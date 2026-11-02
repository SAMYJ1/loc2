"""Local-only, explicit Bluetooth target binding; never starts a positioning session."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .backend import USBBackend
from .wireless import WirelessBackend
from .dual_transport import DualTransportBackend
from .current_network import CurrentNetwork
from .runtime_capabilities import supports_wpa3_transition


def runtime_config(path):
    value={}
    if path.exists():
        if path.stat().st_size > 65536:
            raise ValueError('本机配置文件过大')
        value=json.loads(path.read_text())
        if not isinstance(value,dict): raise ValueError('本机配置格式不正确')
    # Pairing is available before the optional positioning runtime is installed.
    # Respect explicitly configured (including disabled) native or legacy service.
    if 'nativePhone' not in value and 'phone' not in value:
        value['nativePhone']={'port':8767}
    return value


def create_backend(config, runtime, network_requests):
    network=CurrentNetwork(network_requests.put,allow_wpa3_transition=supports_wpa3_transition(runtime)) if config.get('wireless',{}).get('autoNetwork') else None
    if config.get('transport') in ('wireless','auto'):
        settings=config['wireless']
        wireless=WirelessBackend(runtime,settings.get('networkConfig'),legacy_device_id=settings.get('legacyDeviceID'),current_network=network,target_bluetooth=settings.get('targetBluetooth'),wifi_interface=settings.get('wifiInterface','en0'))
        backend=DualTransportBackend(USBBackend(config.get('usbRuntime') or runtime),wireless,config.get('targetUSB')) if config.get('transport')=='auto' else wireless
    else: backend=USBBackend(runtime)
    return backend,network


def _save_config(path, value):
    path=Path(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_uid!=os.getuid():
        raise ValueError('本机配置目录不安全')
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():
            raise ValueError('本机配置文件不安全')
    payload=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
    if len(payload)>65536: raise ValueError('本机配置文件过大')
    descriptor,name=tempfile.mkstemp(prefix='.config-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as file:
            file.write(payload);file.flush();os.fsync(file.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def bind_wireless_target(service, phone, request, config_path, config, runtime, network_requests,
                         backend_factory=create_backend):
    """Only called by the Mac's private JSONL channel, never by a phone API."""
    address=request.get('address')
    if not isinstance(address,str): raise ValueError('未能读取手机蓝牙地址，请重新选择设备')
    address=address.strip().replace('-',':').lower()
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',address) or address in ('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff'):
        raise ValueError('设备蓝牙地址无效，请重新选择手机')
    interface=request.get('wifiInterface')
    if not isinstance(interface,str) or not re.fullmatch(r'en[0-9]+',interface):
        raise ValueError('请先连接 Mac 的 Wi-Fi 网络')
    target='wireless-'+hashlib.sha256(address.encode()).hexdigest()[:20]
    with service.lock:
        if phone is None or not phone.native_pairing or phone.storage_failed:
            raise ValueError('请先扫码并在 Mac 批准手机连接')
        if service.snapshot['sessionId'] or service.snapshot['recovery']=='pending':
            raise ValueError('请先停止当前会话并确认恢复真实位置，再绑定目标')
        matches=[(key,grant) for key,grant in phone.grants.items() if grant['grantId']==request.get('grantId')]
        if len(matches)!=1: raise ValueError('请选择已批准的手机控制端')
        key,grant=matches[0]
        if grant['deviceId'] not in (None,target):
            raise ValueError('此授权已绑定另一目标；请新增扫码授权后再绑定')
        existing=getattr(service.backend,'device_id',None)
        if existing is not None and existing!=target:
            raise ValueError('此 Mac 已配置另一报点目标，不能覆盖现有绑定')
        # Reject external edits instead of silently replacing newer local settings.
        if runtime_config(Path(config_path))!=config:
            raise ValueError('本机配置已变化，请重新打开 App 后再绑定')
        next_config=copy.deepcopy(config)
        if existing is None:
            next_config['transport']='wireless'
            next_config['wireless']={**next_config.get('wireless',{}),'autoNetwork':True,
                'targetBluetooth':address,'wifiInterface':interface}
        backend,network=backend_factory(next_config,runtime,network_requests)
        # Persist configuration before increasing any controller's permissions.
        # A failed grant save leaves a retryable, configured but unbound controller.
        _save_config(config_path,next_config)
        config.clear();config.update(next_config)
        service.backend.stop()
        service.backend=backend
        service.snapshot['controlRevision']+=1
        updated=copy.deepcopy(phone.grants)
        updated[key]['deviceId']=target
        updated[key]['requests']={}
        try: phone.grant_store.save(updated)
        except (OSError,ValueError):
            raise ValueError('蓝牙目标已保存，但授权保存失败；请检查本机存储并重试绑定') from None
        phone.grants=updated
        phone.challenge=None
        phone.pending.clear()
        return network
