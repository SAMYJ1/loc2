"""Current Wi-Fi context from the trusted Mac UI process; never persisted here."""
import copy
import re
import time
import uuid
import threading
from functools import wraps

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
    def __init__(self,request,clock=time.monotonic):
        self.lock=threading.RLock()
        self.request,self.clock=request,clock
        self.metadata=None;self.credentials=None;self.pending=None
        self.updated_at=0;self.failed=False;self.issue=None
        self.hint='应用位置前将自动读取当前 Wi-Fi 连接信息'

    @guarded
    def update_metadata(self,value):
        try:metadata=validate_metadata(value)
        except ValueError:metadata=None
        previous=self.metadata
        changed=previous is not None and (metadata is None or any(metadata[k]!=previous[k] for k in ('ssid','wifiInterface')))
        # A roam within one SSID refreshes connection parameters for the next
        # session; it does not tear down an otherwise healthy current session.
        if previous is not None and metadata!=previous:
            self.credentials=None;self.pending=None;self.failed=False
        self.metadata=metadata;self.updated_at=self.clock()
        if metadata is None:self.credentials=None
        if metadata and self.ready:self.hint=None
        elif not self.pending and not self.failed:self.hint='当前 Wi-Fi 连接参数待自动准备' if metadata else '尚未识别当前 Wi-Fi 网络'
        return changed

    @property
    @guarded
    def ready(self):
        return bool(self.metadata and self.credentials and self.clock()-self.updated_at<12)

    @guarded
    def prepare(self,force=False,interactive=False):
        if self.ready and not interactive:return True
        if self.pending is None and (force or not self.failed):
            self.pending=str(uuid.uuid4());self.hint='正在准备当前 Wi-Fi 连接信息'
            self.request(dict(requestId=self.pending,interactive=bool(interactive)))
        return False

    @guarded
    def complete(self,request_id,value,error=False,reason=None):
        if request_id!=self.pending:return False
        self.pending=None
        if error:
            self.failed=True;self.credentials=None
            self.issue=reason if isinstance(reason,str) and (re.fullmatch(r'(keychain|metadata):-?[0-9]+',reason) or reason in ('network-changed','unsupported-security')) else 'unavailable'
            messages={'unsupported-security':'当前 Wi-Fi 认证方式暂不受无线接收器支持','keychain:4097':'系统凭据接口暂不可用，请稍后重试','keychain:-25300':'当前 Wi-Fi 尚未初始化，请在 Mac 菜单中初始化或更新网络授权',
                      'keychain:-25308':'当前网络授权需要初始化或钥匙串尚未解锁，请在 Mac 菜单中检查；不会自动弹窗',
                      'keychain:-25315':'当前网络授权需要初始化，请在 Mac 菜单中初始化或更新网络授权',
                      'keychain:-25293':'当前网络授权不可用，请在 Mac 菜单中初始化或更新网络授权',
                      'metadata:2':'Mac 未允许读取当前 Wi-Fi 信息，请检查定位服务权限',
                      'network-changed':'网络刚刚发生变化，请重新应用'}
            self.hint=messages.get(self.issue,'当前 Wi-Fi 信息未就绪，请在 Mac 查看网络诊断')
            return False
        try:
            metadata=validate_metadata(value)
            password=value.get('password')
            if not isinstance(password,str) or not password or len(password)>256:raise ValueError('Missing credential')
            if metadata!=self.metadata:raise ValueError('Network changed')
        except (ValueError,AttributeError):
            self.failed=True;self.credentials=None;self.hint='网络已变化或连接信息不完整，请重新应用'
            return False
        self.credentials=dict(metadata,password=password);self.updated_at=self.clock();self.failed=False;self.hint=None;self.issue=None
        return True

    @guarded
    def settings(self):
        if not self.prepare(force=True):raise ValueError(self.hint)
        return copy.deepcopy(self.credentials)
