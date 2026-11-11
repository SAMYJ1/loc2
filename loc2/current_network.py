"""Current Wi-Fi context from the trusted Mac UI process; never persisted here."""
import copy
import re
import time
import uuid
import threading
from functools import wraps

UNSUPPORTED_WPA3 = '当前网络尚未通过无线兼容性检查；WPA3 需要已确认的混合模式及配套运行时，也可使用 USB'
EXPLICIT_REFRESH_REQUIRED = 'Wi-Fi 凭据更新未完成，请在 Mac 菜单中重新初始化或更新网络授权。若 Mac 已锁定，请先解锁'
RETRY_DELAY = 10
RETRYABLE_ISSUES = {
    'keychain:4097': '系统凭据接口暂不可用，Loc2 会自动重试',
    'keychain:-25291': 'macOS 钥匙串暂不可用，Loc2 会自动重试',
    'keychain:-25308': '暂时无法读取钥匙串，Loc2 会自动重试。若 Mac 已锁定，请先解锁。首次连接可在 Mac 菜单中初始化或更新网络授权',
    'network-changed': '当前 Wi-Fi 信息已变化，Loc2 会自动重新检查',
}
ISSUE_HINTS = {
    **RETRYABLE_ISSUES,
    'unsupported-security': '当前 Wi-Fi 认证方式暂不受无线接收器支持',
    'unsupported-wpa3': UNSUPPORTED_WPA3,
    'keychain:-25300': '当前 Wi-Fi 尚未初始化，请在 Mac 菜单中初始化或更新网络授权',
    'keychain:-25315': '当前网络授权需要初始化，请在 Mac 菜单中初始化或更新网络授权',
    'keychain:-25293': '当前网络授权不可用，请在 Mac 菜单中初始化或更新网络授权',
    'metadata:2': 'Mac 未允许读取当前 Wi-Fi 信息，请检查定位服务权限',
    'metadata:3': '尚未识别当前 Wi-Fi 网络，恢复连接后会自动检查',
    'invalid-network-info': '当前 Wi-Fi 信息不完整，请在 Mac 检查当前网络',
}


def require_supported_security(mode, *, reuse_connected_wifi=False):
    # On the tested iOS build, accessoryd rejects iAP security types 3/4 and aborts
    # in WiFiSharing. Preserve the actual network type; never relabel it as WPA2.
    if mode==4 or (mode==3 and not reuse_connected_wifi):raise ValueError(UNSUPPORTED_WPA3)


def guarded(method):
    @wraps(method)
    def invoke(self,*args,**kwargs):
        with self.lock:return method(self,*args,**kwargs)
    return invoke



def validate_metadata(value):
    if not isinstance(value,dict): raise ValueError('当前 Wi-Fi 信息不可用')
    result={key:value.get(key) for key in ('ssid','channel','wifiInterface','accessPointMAC','wifiSecurity')}
    if not isinstance(result['ssid'],str) or not 1<=len(result['ssid'].encode())<=32:
        raise ValueError('当前 Wi-Fi 名称不可用')
    if not isinstance(result['wifiInterface'],str) or not re.fullmatch(r'en[0-9]+',result['wifiInterface']):
        raise ValueError('当前 Wi-Fi 接口无效')
    if type(result['channel']) is not int or not 1<=result['channel']<=196 or result['wifiSecurity'] not in (2,3,4):
        raise ValueError('当前网络认证方式尚不受无线接收器支持')
    if not isinstance(result['accessPointMAC'],str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',result['accessPointMAC']):
        raise ValueError('需要允许 Mac 读取当前 Wi-Fi 信息')
    return result


class CurrentNetwork:
    def __init__(self,request,clock=time.monotonic,allow_wpa3_transition=False):
        self.lock=threading.RLock()
        self.request,self.clock=request,clock
        self.allow_wpa3_transition=bool(allow_wpa3_transition)
        self.metadata = None
        self.credentials = None
        self.pending = None
        self.pending_interactive = False
        self.updated_at = 0
        self.issue = None
        self.retry_at = None
        self.refresh_required_ssids = set()
        self.hint='应用位置前将自动读取当前 Wi-Fi 连接信息'

    @guarded
    def update_metadata(self,value):
        try:metadata=validate_metadata(value)
        except ValueError:metadata=None
        previous=self.metadata
        changed=previous is not None and (metadata is None or any(metadata[k]!=previous[k] for k in ('ssid','wifiInterface')))
        # A roam within one SSID refreshes connection parameters for the next
        # session; it does not tear down an otherwise healthy current session.
        if metadata != previous:
            self.credentials = None
            same_network = previous is not None and metadata is not None and not changed
            if not (same_network and self.issue and self.issue.startswith('keychain:')):
                self.issue = None
                self.retry_at = None
            # Keep an in-flight read when its SSID and interface are unchanged,
            # or when this is the first observation. Successful scan parameters
            # still have to match the current observation in complete().
            if previous is not None and not same_network:
                self.pending = None
                self.pending_interactive = False
            if metadata and self.pending_interactive:
                self.refresh_required_ssids.add(metadata['ssid'])
        self.metadata=metadata;self.updated_at=self.clock()
        if metadata is None:self.credentials=None
        if self._block_unsupported_network():return changed
        if self.issue=='unsupported-wpa3' and (metadata is None or metadata['wifiSecurity']==2):self.issue=None
        if metadata and self.ready:self.hint=None
        elif not self.pending and self.issue is None:
            if metadata and metadata['ssid'] in self.refresh_required_ssids:
                self.hint = EXPLICIT_REFRESH_REQUIRED
            else:
                self.hint = '当前 Wi-Fi 连接参数待自动准备' if metadata else '尚未识别当前 Wi-Fi 网络'
        return changed

    @property
    @guarded
    def ready(self):
        return bool(self.metadata and self.credentials and self.clock()-self.updated_at<12)

    def _block_unsupported_network(self):
        if self.metadata and self.metadata['wifiSecurity'] in (3,4) and not self.allow_wpa3_transition:
            self.pending = None
            self.pending_interactive = False
            self._set_issue('unsupported-wpa3')
            return True
        return False

    def _set_issue(self, issue, *, interactive=False):
        self.credentials = None
        self.issue = issue
        self.retry_at = self.clock() + RETRY_DELAY if not interactive and issue in RETRYABLE_ISSUES else None
        if interactive and (issue in RETRYABLE_ISSUES or issue not in ISSUE_HINTS or issue == 'invalid-network-info'):
            self.hint = EXPLICIT_REFRESH_REQUIRED
        else:
            self.hint = ISSUE_HINTS.get(issue, '当前 Wi-Fi 信息未就绪，请在 Mac 查看网络诊断')

    @guarded
    def prepare(self,force=False,interactive=False):
        if self._block_unsupported_network():return False
        if self.ready and not interactive:return True
        if self.pending is not None and (not interactive or self.pending_interactive):
            return False
        if not interactive and self.refresh_required_ssids:
            if self.metadata is None or self.metadata['ssid'] in self.refresh_required_ssids:
                return False
        retry_due = self.retry_at is not None and self.clock() >= self.retry_at
        if force or interactive or self.issue is None or retry_due:
            if interactive:
                # Silent reads prefer the saved password. Wait for a confirmed
                # explicit save before using that password again for this SSID.
                self.credentials = None
                if self.metadata:
                    self.refresh_required_ssids.add(self.metadata['ssid'])
            self.pending = str(uuid.uuid4())
            self.pending_interactive = bool(interactive)
            self.hint = '正在准备当前 Wi-Fi 连接信息'
            self.request(dict(requestId=self.pending, interactive=self.pending_interactive))
        return False

    @guarded
    def complete(self,request_id,value,error=False,reason=None):
        if self.pending is None or request_id != self.pending:
            return False
        interactive = self.pending_interactive
        self.pending = None
        self.pending_interactive = False
        if error:
            if not isinstance(reason, str) or (reason not in ISSUE_HINTS and not re.fullmatch(r'(keychain|metadata):-?[0-9]+', reason)):
                reason = 'unavailable'
            self._set_issue(reason, interactive=interactive)
            return False
        try:
            metadata=validate_metadata(value)
            password=value.get('password')
            if not isinstance(password,str) or not password or len(password)>256:raise ValueError('Missing credential')
        except (ValueError,AttributeError):
            self._set_issue('invalid-network-info', interactive=interactive)
            return False
        if interactive:
            # A successful reply means the password was saved, even if the scan
            # parameters need to be fetched again for a different access point.
            self.refresh_required_ssids.discard(metadata['ssid'])
        if metadata != self.metadata:
            self._set_issue('network-changed')
            return False
        handshake=value.get('wifiHandshakeSecurity',metadata['wifiSecurity'])
        transition=(self.allow_wpa3_transition and handshake==3 and value.get('wifiAPSupportsTransition') is True)
        if not transition:
            # Old runtimes keep their existing WPA2 path. A WPA3 observation may
            # never be silently relabelled WPA2, even with supplied credentials.
            if metadata['wifiSecurity']!=2 or (self.allow_wpa3_transition and handshake!=2):
                self._set_issue('unsupported-wpa3')
                return False
            handshake=2
        self.credentials=dict(metadata,password=password,wifiHandshakeSecurity=handshake,reuseConnectedWiFi=transition)
        self.updated_at = self.clock()
        self.hint = None
        self.issue = None
        self.retry_at = None
        return True

    @guarded
    def settings(self):
        if not self.prepare(force=True):raise ValueError(self.hint)
        return copy.deepcopy(self.credentials)
