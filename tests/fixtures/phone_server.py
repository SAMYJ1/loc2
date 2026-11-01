"""Browser test fixture: synthetic USB only, private approval through local IPC dispatch."""
import json
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from location_lab.session import SessionService
from location_lab.phone import PhoneControl,PhoneServer
from location_lab.local_host import dispatch

class FixtureUSB:
    def __init__(self): self.devices=['test-phone'];self.running=False
    def device_ids(self): return self.devices.copy()
    def start(self,session,device,emit):
        self.running=True;emit(session,'connected');emit(session,'video-ready');emit(session,'subscribed',active=True)
    def send(self,frame): pass
    def stop(self): self.running=False

usb=FixtureUSB();service=SessionService(usb);service.refresh_devices()
control=PhoneControl(service);server=PhoneServer(('127.0.0.1',0),control,'127.0.0.1')
threading.Thread(target=server.serve_forever,daemon=True).start()
control.create_pairing()
print(json.dumps(control.local_status()),flush=True)
stop=threading.Event()
def tick():
    while not stop.wait(.1): service.tick()
threading.Thread(target=tick,daemon=True).start()
try:
    for line in sys.stdin:
        action=line.strip()
        if action=='approve':
            for pending in control.local_status()['pending']:
                dispatch(service,{'action':'pairing-approve','requestId':pending['requestId']},control)
        elif action=='disconnect': usb.devices=[];service.refresh_devices()
        elif action=='reconnect': usb.devices=['test-phone'];service.refresh_devices()
        elif action=='quit': break
        print(json.dumps({'status':service.status(),'running':usb.running}),flush=True)
finally:
    stop.set();server.shutdown();server.server_close();service.shutdown()
