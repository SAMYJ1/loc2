import json
from pathlib import Path
import tempfile
import time
import unittest
from location_lab.wireless import WirelessBackend,network_config
from location_lab.session import SessionService
from test_runtime_boundary import RECEIVER

class WirelessTests(unittest.TestCase):
    def test_real_receiver_events_use_selected_lane_and_network_loss_ends_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config=root/'network.private.json';config.write_text(json.dumps(dict(ssid='test-network',password='test-only',wifiInterface='en0',targetBluetooth='00:11:22:33:44:55',channel=36)));config.chmod(0o600)
            executable=root/'resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver';executable.parent.mkdir(parents=True)
            source=RECEIVER.replace("print('location: subscribed [1,2]',flush=True)","print('[MVP] location-start channel=wifi [1,2]',flush=True)")
            source=source.replace("{'showCarPlay':True}","{'showCarPlay':False,'hiddenVideoValidation':True}")
            source=source.replace(" if line.strip()=='stop':", " if line.strip()=='subscribe': print('[MVP] location-start channel=bluetooth [1,2]',flush=True)\n if line.strip()=='pause': print('[MVP] location-stop channel=bluetooth',flush=True)\n if line.strip()=='stop':")
            executable.write_text(source);executable.chmod(0o700)
            for name in ['resources/engine/main.js','data/authentication/identity.pk8','data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            address=['192.168.1.2'];usb=[]
            backend=WirelessBackend(root,config,enumerate_devices=lambda:usb,address=lambda _:address[0]);now=[0.0]
            service=SessionService(backend,monotonic=lambda:now[0]);self.addCleanup(service.shutdown)
            service.apply(backend.device_id,dict(latitude=1,longitude=2))
            def wait(predicate):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if predicate(service.status()):return
                    time.sleep(.01)
                self.fail(str(service.status()))
            wait(lambda s:s['videoReady'])
            self.assertFalse(service.status()['subscribed']);service.tick();self.assertEqual(service.status()['helperAcceptedBatches'],0)
            backend.process.stdin.write('subscribe\n');backend.process.stdin.flush();wait(lambda s:s['subscribed'])
            service.tick();self.assertEqual(service.status()['helperAcceptedBatches'],1)
            backend.process.stdin.write('pause\n');backend.process.stdin.flush();wait(lambda s:not s['subscribed']);now[0]=2;service.tick();self.assertEqual(service.status()['helperAcceptedBatches'],1)
            run=backend.run;self.assertFalse((run/'settings.json').exists())
            address[0]='192.168.2.2';service.refresh_devices();self.assertIsNone(service.status()['sessionId']);self.assertFalse(run.exists());self.assertIsNone(backend.awake)
            address[0]='192.168.1.2';service.refresh_devices();service.tick();self.assertIsNone(service.status()['sessionId'])
            usb.append('cabled-phone');self.assertEqual(backend.device_ids(),[])
    def test_private_configuration_rejects_broad_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'network';p.write_text('{}');p.chmod(0o644)
            with self.assertRaises(ValueError):network_config(p)

    def test_stop_marker_is_bound_to_one_run_and_cannot_recreate_deleted_run(self):
        from location_lab.cli import request_stop
        with tempfile.TemporaryDirectory(prefix='ll-',dir='/tmp') as folder:
            root=Path(folder)
            snapshot=dict(sessionActive=True,stopFile=str(root/'STOP'))
            self.assertTrue(request_stop(snapshot));self.assertTrue((root/'STOP').exists())
        with self.assertRaises(FileNotFoundError):request_stop(snapshot)

    def test_stop_is_invisible_until_serialization_finishes(self):
        from unittest.mock import patch
        from location_lab.cli import request_stop
        with tempfile.TemporaryDirectory(prefix='ll-',dir='/tmp') as folder:
            root=Path(folder);snapshot=dict(sessionActive=True,stopFile=str(root/'STOP'))
            original=json.dump
            def write(value,file):
                self.assertFalse((root/'STOP').exists())
                return original(value,file)
            with patch('location_lab.cli.json.dump',side_effect=write):request_stop(snapshot)
            self.assertIsInstance(json.loads((root/'STOP').read_text()),dict)
