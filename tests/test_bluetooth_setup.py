import copy
import hashlib
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from loc2.phone import PhoneControl
from loc2.session import SessionService
from loc2.setup import bind_wireless_target, create_backend, runtime_config
from test_session import USBFixture


class BluetoothSetupTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'config.json'
        self.config=runtime_config(self.path)
        self.backend=USBFixture();self.backend.devices=[]
        self.service=SessionService(self.backend)
        self.phone=PhoneControl(self.service,state_dir=Path(self.folder.name),native_pairing=True)
        challenge=self.phone.create_pairing()['challenge']
        pending=self.phone.request_pairing(dict(challenge=challenge,pollSecret='a'*64,label='Test phone'))
        self.phone.approve(pending['requestId'])
        _,self.token=self.phone.poll_pairing(dict(requestId=pending['requestId'],pollSecret='a'*64))
        self.grant=next(iter(self.phone.grants.values()))['grantId']
        self.request=dict(grantId=self.grant,address='AA-BB-CC-DD-EE-FF',wifiInterface='en1')
        self.target='wireless-'+hashlib.sha256(b'aa:bb:cc:dd:ee:ff').hexdigest()[:20]

    @staticmethod
    def factory(config,runtime,requests):
        backend,network=create_backend(config,runtime,requests)
        wireless=getattr(backend,'wireless',backend)
        wireless.enumerate_devices=lambda:[]
        wireless.address=lambda _: '127.0.0.1'
        return backend,network

    def bind(self):
        return bind_wireless_target(self.service,self.phone,self.request,self.path,self.config,None,queue.Queue(),self.factory)

    def test_binding_persists_without_usb_rescan_or_starting_session(self):
        self.bind()
        self.service.refresh_devices()
        value=self.phone.status(self.token)
        self.assertTrue(value['targetBound'])
        self.assertEqual(value['deviceId'],self.target)
        self.assertIsNone(value['status']['sessionId'])
        self.assertIsNone(self.service.backend.process)
        self.assertEqual(self.config['wireless']['targetBluetooth'],'aa:bb:cc:dd:ee:ff')
        self.assertEqual(self.path.stat().st_mode & 0o077,0)
        restored=PhoneControl(self.service,state_dir=Path(self.folder.name),native_pairing=True)
        self.assertEqual(restored.status(self.token)['deviceId'],self.target)
        new_backend,_=self.factory(runtime_config(self.path),None,queue.Queue())
        self.assertEqual(new_backend.device_id,self.target)

    def test_only_selected_controller_is_bound(self):
        challenge=self.phone.create_pairing()['challenge']
        pending=self.phone.request_pairing(dict(challenge=challenge,pollSecret='b'*64,label='Other phone'))
        self.phone.approve(pending['requestId'])
        _,other=self.phone.poll_pairing(dict(requestId=pending['requestId'],pollSecret='b'*64))
        self.bind()
        self.assertFalse(self.phone.status(other)['targetBound'])

    def test_invalid_grant_address_and_active_session_do_not_write_config(self):
        original=copy.deepcopy(self.request)
        for field,value in [('address','invalid'),('address','00:00:00:00:00:00'),('grantId','unknown'),('wifiInterface','anything')]:
            self.request={**original,field:value}
            with self.assertRaises(ValueError): self.bind()
            self.assertFalse(self.path.exists())
        self.request=original
        for field,value in [('sessionId','active'),('recovery','pending')]:
            before=self.service.snapshot[field];self.service.snapshot[field]=value
            with self.assertRaises(ValueError): self.bind()
            self.service.snapshot[field]=before
            self.assertFalse(self.path.exists())
        self.assertFalse(self.phone.status(self.token)['targetBound'])

    def test_existing_target_and_external_edits_are_preserved(self):
        self.backend.device_id='wireless-another-target'
        with self.assertRaisesRegex(ValueError,'另一报点目标'): self.bind()
        del self.backend.device_id
        self.path.write_text('{"runtime":"/new/location"}')
        with self.assertRaisesRegex(ValueError,'配置已变化'): self.bind()
        self.assertEqual(json.loads(self.path.read_text()),{'runtime':'/new/location'})

    def test_grant_write_failure_is_retryable_without_expanding_permission(self):
        with patch.object(self.phone.grant_store,'save',side_effect=OSError('test')):
            with self.assertRaisesRegex(ValueError,'授权保存失败'): self.bind()
        self.assertFalse(self.phone.status(self.token)['targetBound'])
        self.assertEqual(runtime_config(self.path),self.config)
        self.bind()
        self.assertTrue(self.phone.status(self.token)['targetBound'])

    def test_config_write_failure_preserves_backend_and_grant(self):
        with patch('loc2.setup._save_config',side_effect=OSError('test')):
            with self.assertRaises(OSError): self.bind()
        self.assertIs(self.service.backend,self.backend)
        self.assertFalse(self.phone.status(self.token)['targetBound'])

    def test_existing_dual_transport_settings_are_preserved(self):
        self.config.update(transport='auto',targetUSB='existing-usb',runtime='/private/runtime',
            mobile={'projectRoot':'/private/project'},wireless={'autoNetwork':True,'targetBluetooth':'aa:bb:cc:dd:ee:ff','wifiInterface':'en4'})
        self.path.write_text(json.dumps(self.config))
        self.backend.device_id=self.target
        expected=copy.deepcopy(self.config)
        self.bind()
        self.assertEqual(runtime_config(self.path),expected)
        self.assertEqual(self.service.backend.target_usb,'existing-usb')
        self.assertTrue(self.phone.status(self.token)['targetBound'])
