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
settings=json.load(open(os.environ['MACPLAY_SETTINGS_PATH']))
assert 'wireless' in settings
sock=socket.socket(socket.AF_UNIX);sock.bind(os.environ['MACPLAY_TEST_SOCKET']);sock.listen()
def requests():
 while True:
  c,_=sock.accept()
  with c:
   data=b''
   while b'\\n' not in data and len(data)<10000:
    part=c.recv(1024)
    if not part: break
    data+=part
   frame=base64.b64decode(data.split(b' ',1)[1].strip())
   valid=frame.startswith(b'$GPGGA,') and b'$GPRMC,' in frame
   c.sendall(json.dumps({'ok':valid}).encode()+b'\\n')
   print('[MVP] location-message-queued',flush=True)
threading.Thread(target=requests,daemon=True).start()
print('wired: MFi auth succeeded',flush=True)
print('location: subscribed [1,2]',flush=True)
print(json.dumps({'showCarPlay':True}),flush=True)
for line in sys.stdin:
 if line.strip()=='stop':
  # Fill output far beyond a pipe buffer during shutdown; reader must keep draining.
  for i in range(10000): print('location: stopped')
  sys.stdout.flush()
  break
'''

class RuntimeBoundaryTests(unittest.TestCase):
    def test_wireless_wpa3_is_blocked_at_process_launch_boundary(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver',
                         'resources/engine/main.js','data/authentication/identity.pk8',
                         'data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture');path.chmod(0o700)
            backend=USBBackend(root)
            backend.settings=lambda device:dict(wireless=True,wifiSecurity=4)
            with patch('location_lab.backend.subprocess.Popen',side_effect=AssertionError('receiver must not launch')) as launch:
                with self.assertRaisesRegex(ValueError,'WPA3'):
                    backend.start('fixture','fixture-phone',lambda *a,**kw:None)
                launch.assert_not_called()
            self.assertIsNone(backend.run)

    def test_wireless_handoff_diagnostics_survive_adapter_without_private_details(self):
        lines = [
            '[cp] CarPlayAvailability wired=None wireless=Some(CarPlayAvailabilityWirelessAttributes { available: Some(false), bluetooth_transport_identifier: Some("private-device") })',
            '[cp] bluetooth: CarPlayStartSession sent',
            '{"stage":"network-discovery","detail":"网络发现：IPv6多播警告/EINVAL private-secret"}',
            '{"stage":"network-handoff-started","detail":"private-secret"}',
            '{"stage":"handoff-summary","detail":{"discoverySockets":1,"discoveryResponses":12,"controlServices":0,"probeEndpoints":0,"probeAccepted":0,"secret":"private-secret"}}',
        ]
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            executable=root/'resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/usr/bin/python3\nimport sys\n'+''.join(f'print({line!r},flush=True)\n' for line in lines)+'for line in sys.stdin:\n if line.strip()=="stop": break\n')
            executable.chmod(0o700)
            for name in ('resources/engine/main.js','data/authentication/identity.pk8','data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            backend=USBBackend(root,enumerate_devices=lambda:['fixture-phone'])
            backend.lane='bluetooth'
            service=SessionService(backend)
            try:
                service.apply('fixture-phone',{'latitude':1,'longitude':2})
                result=self.await_status(service,lambda s:len(s['diagnosticEvents'])>=5,'wireless handoff diagnostic trace')
                stages=[e['stage'] for e in result['diagnosticEvents']]
                self.assertIn('carplay-wireless-unavailable',stages)
                self.assertIn('network-handoff-started',stages)
                self.assertIn('discovery-ipv6-warning-EINVAL',stages)
                self.assertIn('discovery-summary:sockets=1,responses=12,services=0,endpoints=0,accepted=0',stages)
                self.assertNotIn('private-',json.dumps(result))
                self.assertEqual(result['helperAcceptedBatches'],0)
            finally:service.shutdown()

    def await_status(self, service, predicate, description):
        # Readiness comes from the external receiver's actual subscription events.
        # Keep wall-clock scheduling out of the service throttle/clock-gap tests.
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            status=service.status()
            if predicate(status): return status
            self.assertNotEqual(status['state'],'error',f'{description}: {status}')
            time.sleep(.01)
        self.fail(f'Timed out waiting for {description}: {service.status()}')

    def test_real_adapter_lifecycle_under_log_pressure_through_session_service(self):
        self.exercise_receiver({'showCarPlay':True})

    def test_hidden_video_ready_signal_also_releases_location_supply(self):
        self.exercise_receiver({'showCarPlay':False,'hiddenVideoValidation':True})

    def test_authentication_socket_survives_long_install_path(self):
        self.exercise_receiver({'showCarPlay':False,'hiddenVideoValidation':True},long_data=True)

    def exercise_receiver(self, ready_event, long_data=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/("installed-runtime-"+"x"*100) if long_data else Path(directory)
            executable=root/'resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver'
            executable.parent.mkdir(parents=True)
            source=RECEIVER.replace("{'showCarPlay':True}",repr(ready_event))
            if long_data:
                source=source.replace("sock=socket.socket", "bluetooth=socket.socket(socket.AF_UNIX);bluetooth.bind(os.path.join(os.environ['MACPLAY_DATA'],'authentication','bluetooth.sock'))\nsock=socket.socket",1)
            executable.write_text(source);executable.chmod(0o700)
            for name in ('resources/engine/main.js','data/authentication/identity.pk8',
                         'data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('test fixture only')
            service=SessionService(USBBackend(root,enumerate_devices=lambda:['fixture-phone']),monotonic=lambda:0)
            try:
                service.apply('fixture-phone',{'latitude':1,'longitude':2})
                self.await_status(service,lambda s:s['connected'] and s['videoReady'] and s['subscribed'],'receiver subscription')
                service.tick()
                self.await_status(service,lambda s:s['queuedMessages']>0,'receiver queue acknowledgement')
                self.assertEqual(service.status()['helperAcceptedBatches'],1)
                self.assertGreater(service.status()['queuedMessages'],0)
                started=time.monotonic();service.stop()
                self.assertLess(time.monotonic()-started,2)
                self.assertIsNone(service.status()['sessionId'])
                self.assertEqual((root/'data/authentication/identity.pk8').read_text(),'test fixture only')
                self.assertEqual(service.status()['recovery'],'pending')
            finally: service.shutdown()
