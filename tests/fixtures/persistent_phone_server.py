"""Private persistent-browser fixture with synthetic USB; never accesses real hardware."""
import argparse
import json
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_session import USBFixture
from location_lab.session import SessionService
from location_lab.phone import PhoneControl,PhoneServer
from location_lab.local_host import dispatch

class ConnectedUSB(USBFixture):
    def start(self,session,device,emit):
        super().start(session,device,emit)
        emit(session,'connected');emit(session,'subscribed',active=True)

parser=argparse.ArgumentParser();parser.add_argument('--state-dir',required=True);parser.add_argument('--port',type=int,default=0)
args=parser.parse_args()
usb=ConnectedUSB();service=SessionService(usb);service.refresh_devices()
control=PhoneControl(service,state_dir=Path(args.state_dir));server=PhoneServer(('127.0.0.1',args.port),control,'127.0.0.1')
threading.Thread(target=server.serve_forever,daemon=True).start()
control.create_pairing();print(json.dumps(dict(control.local_status(),port=server.server_port)),flush=True)
stop=threading.Event()
def tick():
    while not stop.wait(.1): service.tick()
threading.Thread(target=tick,daemon=True).start()
try:
    for line in sys.stdin:
        action=line.strip()
        if action=='approve':
            for pending in control.local_status()['pending']:
                dispatch(service,dict(action='pairing-approve',requestId=pending['requestId']),control)
        elif action=='revoke':
            for grant in control.local_status()['grants']:
                dispatch(service,dict(action='pairing-revoke',grantId=grant['grantId']),control)
        elif action=='pair': control.create_pairing()
        elif action=='stop': service.stop()
        elif action=='quit': break
        print(json.dumps(dict(status=service.status(),running=usb.running,phone=control.local_status())),flush=True)
finally:
    stop.set();server.shutdown();server.server_close();service.shutdown()
