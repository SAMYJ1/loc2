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
from .session import SessionService
from .phone import PhoneControl, PhoneServer
from .grants import AuthorizationStorageError
from .favorites import FavoritesStorageError


def runtime_config(path):
    if not path.exists(): return {}
    if path.stat().st_size > 65536:
        raise ValueError('本机配置文件过大')
    value=json.loads(path.read_text())
    if not isinstance(value,dict): raise ValueError('本机配置格式不正确')
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
    if action=='status': return service.status()
    if action=='apply':
        service.refresh_devices()
        return service.apply(request.get('deviceId'),request.get('point'),request.get('sessionId'))
    if action=='stop': return service.stop(expected_session_id=request.get('sessionId'))
    if action=='sleep': return service.suspend()
    if action=='quit': return service.shutdown()
    if action=='confirm-adoption': return service.confirm_adoption(request.get('sessionId'))
    if action=='confirm-recovery': return service.confirm_recovery()
    raise ValueError('不支持的本机操作')


def main():
    parser=argparse.ArgumentParser(description='Location Lab private menu host; no USB until explicit apply')
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/location-lab/config.json')
    args=parser.parse_args()
    config=runtime_config(args.config)
    service=SessionService(USBBackend(args.runtime or config.get('runtime')))
    phone,phone_server,phone_error=None,None,None
    if config.get('phone'):
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
    try:
        while not done.is_set():
            if time.monotonic()>=refresh_at:
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
            response['phone']=phone.local_status() if phone else dict(error=phone_error or '请配置本机 phone 局域网地址以启用手机控制',pending=[])
            try:
                print(json.dumps(response,ensure_ascii=False,allow_nan=False),flush=True)
            except BrokenPipeError:
                done.set()
            if isinstance(request,dict) and request.get('action')=='quit': done.set()
            service.tick()
    finally:
        if phone_server:
            phone_server.shutdown();phone_server.server_close()
        service.shutdown()


if __name__=='__main__': main()
