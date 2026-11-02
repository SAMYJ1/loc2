"""Selected-device wireless adapter. Credentials stay in restricted local configuration."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from .backend import USBBackend, usb_devices
from .current_network import require_supported_security


def default_route_interface(run=subprocess.run):
    try:
        result=run(['/sbin/route','-n','get','default'],capture_output=True,text=True,timeout=3)
    except (OSError,subprocess.TimeoutExpired):
        return ''
    if result.returncode != 0:return ''
    match=re.search(r'^\s*interface:\s*([A-Za-z0-9][A-Za-z0-9._-]{0,31})\s*$',result.stdout,re.MULTILINE)
    return match.group(1) if match else ''


def interface_address(interface=None,run=subprocess.run):
    interface=interface or default_route_interface(run)
    if not isinstance(interface,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,31}',interface):return ''
    try:
        result=run(['/usr/sbin/ipconfig','getifaddr',interface],capture_output=True,text=True,timeout=3)
    except (OSError,subprocess.TimeoutExpired):
        return ''
    address = result.stdout.strip()
    try:
        parsed=ipaddress.ip_address(address)
        return address if result.returncode == 0 and parsed.version == 4 and parsed.is_private else ''
    except ValueError:
        return ''


def network_config(path):
    path=Path(path).expanduser()
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>16384:
            raise ValueError('无线配置必须为当前用户的私有文件')
        value=json.load(source)
    if not isinstance(value,dict): raise ValueError('无线配置无效')
    if any(not isinstance(value.get(k),str) or not value[k] for k in ('ssid','password','wifiInterface','targetBluetooth')):
        raise ValueError('请先完成本机无线网络配置')
    if not re.fullmatch(r'en[0-9]+',value['wifiInterface']) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value['targetBluetooth']):
        raise ValueError('无线接口或目标设备无效')
    if type(value.get('channel')) is not int or not 1<=value['channel']<=196 or value.get('wifiSecurity',2) not in (2,3,4):
        raise ValueError('无线网络参数无效')
    require_supported_security(value.get('wifiSecurity',2))
    return value


class WirelessBackend(USBBackend):
    lane='bluetooth'
    def __init__(self,workspace,configuration=None,enumerate_devices=usb_devices,address=interface_address,legacy_device_id=None,current_network=None,target_bluetooth=None,wifi_interface="en0"):
        super().__init__(workspace,enumerate_devices)
        self.network_path=Path(configuration).expanduser() if configuration else None
        self.address=address
        self.legacy_device_id=legacy_device_id
        self.current_network=current_network
        if current_network:
            if not isinstance(target_bluetooth,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',target_bluetooth):
                raise ValueError('请先绑定目标 iPhone')
            self.network=dict(targetBluetooth=target_bluetooth,wifiInterface=wifi_interface)
        else:self.network=network_config(self.network_path)
        self.device_id='wireless-'+hashlib.sha256(self.network['targetBluetooth'].lower().encode()).hexdigest()[:20]
        self.initial_address=None
        self.awake=None
        self.unavailable_reason=None

    def device_ids(self):
        # A USB cable invalidates this explicitly wireless path; never fall back silently.
        if self.enumerate_devices():
            self.unavailable_reason='无线模式需要拔掉 iPhone 与 Mac 之间的 USB 线'
            return []
        current=self.address(self.network['wifiInterface'])
        if not current:
            self.unavailable_reason='Mac 当前没有可用的 Wi-Fi 网络地址'
            return []
        if self.initial_address and current!=self.initial_address:
            self.unavailable_reason='网络已变化，请重新连接后应用位置'
            return []
        self.unavailable_reason=self.current_network.hint if self.current_network and not self.current_network.ready and self.process is None else None
        return [self.device_id]

    def prepare_for_apply(self):
        if self.current_network and not self.current_network.prepare(force=True):
            raise ValueError(self.current_network.hint)

    def settings(self,device_id):
        if device_id!=self.device_id or self.device_ids()!=[device_id]: raise ValueError('无线目标不可用')
        self.initial_address=self.address(self.network['wifiInterface'])
        settings=super().settings('')
        network=dict(self.network)
        if self.current_network:network.update(self.current_network.settings())
        settings.update({k:v for k,v in network.items() if k in ('ssid','password','wifiInterface','channel','targetBluetooth','accessPointMAC','wifiSecurity')})
        if self.current_network:
            settings['wifiSecurity']=network['wifiHandshakeSecurity']
            settings['reuseConnectedWiFi']=network['reuseConnectedWiFi']
        settings['wireless']=True
        return settings

    def start(self,session_id,device_id,emit):
        try:
            super().start(session_id,device_id,emit)
            # Prevent idle system sleep, not display sleep or an explicit user sleep.
            self.awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(self.process.pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:
            self.stop()
            raise

    def stop(self):
        super().stop()
        if self.awake:
            if self.awake.poll() is None: self.awake.terminate()
            try: self.awake.wait(timeout=3)
            except subprocess.TimeoutExpired: self.awake.kill();self.awake.wait()
        self.awake=None
        self.initial_address=None
