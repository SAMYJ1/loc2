"""Private JSONL host for the native menu application; stdin EOF ends USB activity."""
import argparse
import json
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time
from .backend import USBBackend
from .wireless import WirelessBackend, interface_address
from .dual_transport import DualTransportBackend
from .usb_control import USBControlBridge
from .native_server import NativeServer
from .current_network import CurrentNetwork
from .runtime_capabilities import supports_wpa3_transition
import subprocess
from .session import SessionService
from .phone import PhoneControl, PhoneServer
from .grants import AuthorizationStorageError
from .favorites import FavoritesStorageError


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
        value['nativePhone']={'interface':'en0','port':8767}
    return value


def dispatch(service, request, phone=None):
    action=request.get('action')
    if isinstance(action,str) and action.startswith('pairing-'):
        if phone is None: raise ValueError('请先在本机配置 phone 局域网地址并重新打开应用')
        if action=='pairing-create': phone.create_pairing()
        elif action=='pairing-approve': phone.approve(request.get('requestId'))
        elif action=='pairing-revoke': phone.revoke(request.get('grantId'))
        elif action=='pairing-deny': phone.deny(request.get('requestId'))
        elif action!='pairing-status': raise ValueError('不支持的配对操作')
        return service.status()
    if action in ('network-prepare','network-authorize'):
        network=getattr(service.backend,'current_network',None)
        if network is None:raise ValueError('当前未启用自动网络信息')
        network.prepare(force=True,interactive=action=='network-authorize')
        return service.refresh_devices()
    if action in ('network-status','network-update'):
        network=getattr(service.backend,'current_network',None)
        if network is None:raise ValueError('当前未启用自动网络信息')
        with service.lock:
            if action=='network-status':
                changed=network.update_metadata(request.get('network'))
                if changed and getattr(service.backend,'requires_network',True):
                    if service.snapshot['sessionId']:service.stop('network-changed')
                    else:service.snapshot['controlRevision']+=1
            else:network.complete(request.get('requestId'),request.get('network'),bool(request.get('error')),request.get('reason'))
            service.refresh_devices()
            return service.status()
    if action=='status': return service.status()
    if action=='apply':
        service.refresh_devices()
        return service.apply(request.get('deviceId'),request.get('point'),request.get('sessionId'))
    if action=='stop': return service.stop(expected_session_id=request.get('sessionId'))
    if action=='sleep': return service.suspend()
    if action=='quit': return service.shutdown()
    if action=='confirm-adoption': return service.confirm_adoption(request.get('sessionId'),request.get('controlRevision'))
    if action=='confirm-recovery': return service.confirm_recovery(request.get('controlRevision'))
    raise ValueError('不支持的本机操作')


def main():
    parser=argparse.ArgumentParser(description='loc2 private menu host; no USB until explicit apply')
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/loc2/config.json')
    args=parser.parse_args()
    config=runtime_config(args.config)
    runtime=args.runtime or config.get('runtime')
    network_requests=queue.Queue()
    dynamic_network=CurrentNetwork(network_requests.put,allow_wpa3_transition=supports_wpa3_transition(runtime)) if config.get('wireless',{}).get('autoNetwork') else None
    if config.get('transport') in ('wireless','auto'):
        wireless=WirelessBackend(runtime,config['wireless'].get('networkConfig'),legacy_device_id=config['wireless'].get('legacyDeviceID'),current_network=dynamic_network,target_bluetooth=config['wireless'].get('targetBluetooth'),wifi_interface=config['wireless'].get('wifiInterface','en0'))
        backend=DualTransportBackend(USBBackend(config.get('usbRuntime') or runtime),wireless,config.get('targetUSB')) if config.get('transport')=='auto' else wireless
    else:backend=USBBackend(runtime)
    service=SessionService(backend)
    phone,phone_server,phone_error=None,None,None
    usb_server,usb_bridge=None,None
    if config.get('nativePhone'):
        try:
            settings=config['nativePhone']
            state_dir=Path(config.get('stateDirectory',args.config.parent)).expanduser()
            state_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
            phone=PhoneControl(service,state_dir=state_dir,maps_config=config.get('maps'))
            bind=settings.get('bindAddress') or interface_address(settings.get('interface','en0'))
            host=settings.get('advertisedHost')
            if not host:
                query=subprocess.run(['/usr/sbin/scutil','--get','LocalHostName'],capture_output=True,text=True,timeout=3)
                host=query.stdout.strip()+'.local' if query.returncode==0 else bind or 'localhost'
            if config.get('transport')=='auto':
                usb_server=NativeServer(('127.0.0.1',0),phone,host,state_dir)
                # Pairing always stores the stable LAN endpoint. USB overrides only
                # the socket destination and still verifies this host and certificate.
                usb_server.origin=f'https://{host}:{int(settings.get("port",8767))}'
                threading.Thread(target=usb_server.serve_forever,daemon=True).start()
                usb_bridge=USBControlBridge(config['targetUSB'],usb_server.server_port)
                usb_bridge.start()
            if bind:
                phone_server=NativeServer((bind,int(settings.get('port',8767))),phone,host,state_dir)
                threading.Thread(target=phone_server.serve_forever,daemon=True).start()
            else:phone_error='局域网控制不可用；可连接 USB 使用手机控制'
        except (ValueError,KeyError,TypeError,OSError):
            if usb_server is None:phone=None
            phone_error='原生手机网络服务无法启动，请检查网络及本机身份配置'
    elif config.get('phone'):
        try:
            settings=config['phone']
            phone=PhoneControl(service,state_dir=Path(config.get('stateDirectory',args.config.parent)).expanduser(),maps_config=config.get('maps'))
            phone_server=PhoneServer((settings['bindAddress'],int(settings.get('port',8765))),phone,settings['advertisedHost'])
            threading.Thread(target=phone_server.serve_forever,daemon=True).start()
        except (AuthorizationStorageError,FavoritesStorageError) as error:
            phone=None;phone_error=str(error)
        except (ValueError,KeyError,TypeError,OSError):
            phone=None;phone_error='手机控制服务无法启动，请检查本机 phone 地址配置'
    requests=queue.Queue()
    done=threading.Event()
    def interrupted(signum,frame): done.set()
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    def read_input():
        while not done.is_set():
            line=sys.stdin.readline(65537)
            if not line: done.set();return
            if len(line)>65536: done.set();return
            requests.put(line)
    threading.Thread(target=read_input,daemon=True).start()
    refresh_at=0
    diagnostics_at=0
    diagnostics_path=Path(config.get('stateDirectory',args.config.parent)).expanduser()/'latest-status.private.json'

    try:
        while not done.is_set():
            try:network_request=network_requests.get_nowait()
            except queue.Empty:network_request=None
            if network_request:
                print(json.dumps(dict(event='network-request',**network_request)),flush=True)
            if time.monotonic()>=diagnostics_at:
                try:
                    current=service.status()
                    fields=('connectionHint','state','connected','subscribed','videoReady','helperAcceptedBatches','targetAcceptedBatches',
                            'queuedMessages','diagnosticStage','diagnosticEvents','videoReceivedFrames','videoDecodedFrames','error','stopReason','transport','availableTransport','transportPolicy')
                    summary={key:current.get(key) for key in fields}
                    summary['networkIssue']=dynamic_network.issue if dynamic_network else None
                    summary['usbControlConnected']=bool(usb_bridge and usb_bridge.connected)
                    summary.update(sessionActive=bool(current.get('sessionId')),updatedAt=time.time(),controlEpoch=current['controlEpoch'],controlRevision=current['controlRevision'],sessionId=current.get('sessionId'),stopFile=str(service.backend.run/'STOP') if getattr(service.backend,'run',None) else None)
                    temporary=diagnostics_path.with_suffix('.tmp')
                    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w') as file: json.dump(summary,file,ensure_ascii=False)
                    os.replace(temporary,diagnostics_path)
                except (OSError,ValueError): pass
                diagnostics_at=time.monotonic()+1
            if time.monotonic()>=refresh_at:
                if config.get('nativePhone'):
                    settings=config['nativePhone']
                    desired=settings.get('bindAddress') or interface_address(settings.get('interface','en0'))
                    if phone_server is None or phone_server.server_address[0]!=desired:
                        if phone_server:
                            phone_server.shutdown();phone_server.server_close();phone_server=None
                        phone_error='Mac 当前不在可用局域网，连接后会自动恢复控制服务'
                        if desired:
                            try:
                                state_dir=Path(config.get('stateDirectory',args.config.parent)).expanduser()
                                if phone is None: phone=PhoneControl(service,state_dir=state_dir,maps_config=config.get('maps'))
                                host=settings.get('advertisedHost')
                                if not host:
                                    query=subprocess.run(['/usr/sbin/scutil','--get','LocalHostName'],capture_output=True,text=True,timeout=3)
                                    host=query.stdout.strip()+'.local' if query.returncode==0 else desired
                                phone_server=NativeServer((desired,int(settings.get('port',8767))),phone,host,state_dir)
                                threading.Thread(target=phone_server.serve_forever,daemon=True).start();phone_error=None
                            except (ValueError,KeyError,TypeError,OSError):
                                phone_server=None;phone_error='原生手机服务暂不可用，请检查本机网络或身份配置'
                try: service.refresh_devices()
                except Exception:
                    # No raw OS paths or backend messages cross this boundary.
                    service.stop('usb-enumeration-unavailable')
                refresh_at=time.monotonic()+2
            try: line=requests.get(timeout=.1)
            except queue.Empty:
                service.tick();continue
            request={}
            try:
                request=json.loads(line)
                if not isinstance(request,dict): raise ValueError('请求必须为对象')
                result=dispatch(service,request,phone)
                response=dict(id=request.get('id'),ok=True,status=result)
            except ValueError as error:
                response=dict(id=request.get('id') if isinstance(request,dict) else None,
                              ok=False,error=str(error),status=service.status())
            except Exception:
                response=dict(id=request.get('id'),ok=False,error='本机操作失败，请检查运行时配置',status=service.status())
            response['networkAutoEnabled']=dynamic_network is not None
            native_server=phone_server if isinstance(phone_server,NativeServer) else usb_server
            response['phone']=native_server.local_status() if native_server else phone.local_status() if phone else dict(error=phone_error or '请配置本机 phone 局域网地址以启用手机控制',pending=[])
            response['phone']['usbControlConnected']=bool(usb_bridge and usb_bridge.connected)
            if config.get('nativePhone') and phone_server is None and usb_server is None: response['phone']['error']=phone_error
            try:
                print(json.dumps(response,ensure_ascii=False,allow_nan=False),flush=True)
            except BrokenPipeError:
                done.set()
            if isinstance(request,dict) and request.get('action')=='quit': done.set()
            service.tick()
    finally:
        if usb_bridge:usb_bridge.stop()
        if usb_server:usb_server.shutdown();usb_server.server_close()
        if phone_server:
            phone_server.shutdown();phone_server.server_close()
        service.shutdown()


if __name__=='__main__': main()
