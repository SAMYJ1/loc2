"""Session-service integration against an external fake receiver, never USB hardware."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from location_lab.backend import USBBackend
from location_lab.session import SessionService

RECEIVER = '''#!/usr/bin/python3
import base64,json,os,socket,sys,threading
sock=socket.socket(socket.AF_UNIX);sock.bind(os.environ['MACPLAY_TEST_SOCKET']);sock.listen()
def requests():
 while True:
  c,_=sock.accept()
  with c:
   data=c.recv(10000)
   frame=base64.b64decode(data.split(b' ',1)[1].strip())
   valid=frame.startswith(b'$GPGGA,') and b'$GPRMC,' in frame
   c.sendall(json.dumps({'ok':valid}).encode()+b'\\n')
   print('[MVP] location-message-queued',flush=True)
threading.Thread(target=requests,daemon=True).start()
print('wired: MFi auth succeeded',flush=True)
print('location: subscribed [1,2]',flush=True)
for line in sys.stdin:
 if line.strip()=='stop':
  # Fill output far beyond a pipe buffer during shutdown; reader must keep draining.
  for i in range(10000): print('location: stopped')
  sys.stdout.flush()
  break
'''

class RuntimeBoundaryTests(unittest.TestCase):
    def test_real_adapter_lifecycle_under_log_pressure_through_session_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            executable=root/'resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'
            executable.parent.mkdir(parents=True);executable.write_text(RECEIVER);executable.chmod(0o700)
            for name in ('resources/engine/main.js','data/authentication/identity.pk8',
                         'data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('test fixture only')
            service=SessionService(USBBackend(root,enumerate_devices=lambda:['fixture-phone']))
            try:
                service.apply('fixture-phone',{'latitude':1,'longitude':2})
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and service.status()['queuedMessages']==0:
                    service.tick();time.sleep(.02)
                self.assertEqual(service.status()['helperAcceptedBatches'],1)
                self.assertGreater(service.status()['queuedMessages'],0)
                started=time.monotonic();service.stop()
                self.assertLess(time.monotonic()-started,2)
                self.assertIsNone(service.status()['sessionId'])
                self.assertEqual(service.status()['recovery'],'pending')
            finally: service.shutdown()
