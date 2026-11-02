import json
from pathlib import Path
import tempfile
import time
import unittest
from loc2.wireless import WirelessBackend,network_config
from loc2.session import SessionService
from test_runtime_boundary import RECEIVER

class WirelessTests(unittest.TestCase):
    def test_verified_transition_reaches_receiver_without_legacy_wifi_sharing(self):
        import hashlib
        from loc2.current_network import CurrentNetwork
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            executable=root/'resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver';executable.parent.mkdir(parents=True)
            source=RECEIVER.replace("assert 'wireless' in settings", "assert settings['wifiSecurity']==3\nassert os.environ['MACPLAY_REUSE_CONNECTED_WIFI']=='1'\nopen(os.path.join(os.environ['MACPLAY_RESOURCES'],'started'),'w').close()")
            source=source.replace("print('location: subscribed [1,2]',flush=True)","print('[MVP] location-start channel=bluetooth [1,2]',flush=True)")
            executable.write_text(source);executable.chmod(0o700)
            for name in ('resources/engine/main.js','data/authentication/identity.pk8','data/authentication/certificate.p7b','data/cp/macplay-v3/identity.json'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            driver=root/'resources/driver';driver.mkdir();helper=driver/'livi-helperd';helper.write_bytes(b'transition-fixture')
            (driver/'loc2-capabilities.json').write_text(json.dumps(dict(schemaVersion=1,wpa3Transition=True,
                helperSHA256=hashlib.sha256(helper.read_bytes()).hexdigest())))
            requests=[];network=CurrentNetwork(requests.append,allow_wpa3_transition=True)
            metadata=dict(ssid='fixture',channel=40,wifiInterface='en0',accessPointMAC='00:11:22:33:44:55',wifiSecurity=4)
            network.update_metadata(metadata);network.prepare()
            self.assertTrue(network.complete(requests[-1]['requestId'],dict(metadata,password='test-only',wifiHandshakeSecurity=3,wifiAPSupportsTransition=True)))
            backend=WirelessBackend(root,current_network=network,target_bluetooth='00:11:22:33:44:66',enumerate_devices=lambda:[],address=lambda _: '192.168.1.2')
            service=SessionService(backend);self.addCleanup(service.shutdown)
            service.apply(backend.device_id,dict(latitude=1,longitude=2))
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and not service.status()['videoReady']:time.sleep(.01)
            self.assertTrue(service.status()['videoReady']);self.assertTrue(service.status()['subscribed'])
            service.tick();self.assertEqual(service.status()['helperAcceptedBatches'],1)
            service.stop();(root/'resources/started').unlink()
            helper.write_bytes(b'old-helper-without-capability')
            with self.assertRaises(ValueError):service.apply(backend.device_id,dict(latitude=1,longitude=2))
            self.assertFalse((root/'resources/started').exists());self.assertIsNone(backend.process)

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

    def test_legacy_configuration_cannot_send_the_rejected_wpa3_security_type(self):
        with tempfile.TemporaryDirectory() as folder:
            for mode in (3,4):
                p=Path(folder)/'network';p.write_text(json.dumps(dict(ssid='test-network',password='test-only',
                    wifiInterface='en0',targetBluetooth='00:11:22:33:44:55',channel=48,wifiSecurity=mode)));p.chmod(0o600)
                with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'WPA3'):network_config(p)

    def test_stop_marker_is_bound_to_one_run_and_cannot_recreate_deleted_run(self):
        from loc2.cli import request_stop
        with tempfile.TemporaryDirectory(prefix='loc2-',dir='/tmp') as folder:
            root=Path(folder)
            snapshot=dict(sessionActive=True,stopFile=str(root/'STOP'))
            self.assertTrue(request_stop(snapshot));self.assertTrue((root/'STOP').exists())
        with self.assertRaises(FileNotFoundError):request_stop(snapshot)

    def test_stop_is_invisible_until_serialization_finishes(self):
        from unittest.mock import patch
        from loc2.cli import request_stop
        with tempfile.TemporaryDirectory(prefix='loc2-',dir='/tmp') as folder:
            root=Path(folder);snapshot=dict(sessionActive=True,stopFile=str(root/'STOP'))
            original=json.dump
            def write(value,file):
                self.assertFalse((root/'STOP').exists())
                return original(value,file)
            with patch('loc2.cli.json.dump',side_effect=write):request_stop(snapshot)
            self.assertIsInstance(json.loads((root/'STOP').read_text()),dict)
