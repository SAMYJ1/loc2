import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from location_lab.phone import PhoneControl, RequestError
from location_lab.local_host import dispatch
from location_lab.session import SessionService
from test_session import USBFixture

class PersistentAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'private'
        self.usb=USBFixture();self.service=SessionService(self.usb);self.service.refresh_devices()
    def pair(self,control):
        challenge=control.create_pairing()['challenge']
        pending=control.request_pairing(dict(challenge=challenge,pollSecret='a'*64,label='Safari'))
        control.approve(pending['requestId'])
        _,token=control.poll_pairing(dict(requestId=pending['requestId'],pollSecret='a'*64))
        return token
    def test_restart_preserves_authorization_but_never_session_or_epoch(self):
        control=PhoneControl(self.service,state_dir=self.directory)
        token=self.pair(control)
        self.service.apply('test-phone',dict(latitude=1,longitude=2))
        old=self.service.status();self.service.shutdown()
        replacement=SessionService(self.usb);replacement.refresh_devices()
        restarted=PhoneControl(replacement,state_dir=self.directory)
        snapshot=restarted.status(token)['status']
        self.assertIsNone(snapshot['sessionId']);self.assertIsNone(snapshot['target'])
        self.assertNotEqual(snapshot['controlEpoch'],old['controlEpoch'])
        self.assertFalse(self.usb.running)
        contents=(self.directory/'grants.json').read_text()
        self.assertNotIn(token,contents)
        self.assertNotIn(old['controlEpoch'],contents)
        self.assertNotIn('requests',contents)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((self.directory/'grants.json').stat().st_mode),0o600)
    def test_local_revoke_is_immediate_and_survives_restart(self):
        control=PhoneControl(self.service,state_dir=self.directory);token=self.pair(control)
        grants=control.local_status()['grants']
        self.assertEqual(len(grants),1);self.assertNotIn('token',grants[0])
        dispatch(self.service,{'action':'pairing-revoke','grantId':grants[0]['grantId']},control)
        with self.assertRaises(RequestError): control.status(token)
        restarted=PhoneControl(self.service,state_dir=self.directory)
        with self.assertRaises(RequestError): restarted.status(token)
        self.assertEqual(restarted.local_status()['grants'],[])
    def test_unsafe_or_corrupt_storage_fails_closed_without_overwrite(self):
        self.directory.mkdir(mode=0o700)
        path=self.directory/'grants.json'
        for invalid in ['not json','{}','{"version":1,"grants":[]}', 'x'*65537]:
            path.write_text(invalid);path.chmod(0o600)
            with self.assertRaises(ValueError): PhoneControl(self.service,state_dir=self.directory)
            self.assertEqual(path.read_text(),invalid)
        path.unlink();outside=Path(self.temp.name)/'outside';outside.write_text('{"version":1,"grants":{}}')
        path.symlink_to(outside)
        with self.assertRaises(ValueError): PhoneControl(self.service,state_dir=self.directory)
        self.assertTrue(path.is_symlink())
    def test_previous_epoch_command_is_rejected_after_restart_with_saved_cookie(self):
        control=PhoneControl(self.service,state_dir=self.directory);token=self.pair(control)
        snapshot=self.service.status()
        request=dict(deviceId='test-phone',requestId='queued-before-restart',timestamp=control.clock(),
                     expectedRevision=snapshot['controlRevision'],expectedEpoch=snapshot['controlEpoch'],point=dict(latitude=1,longitude=2))
        replacement=SessionService(self.usb);replacement.refresh_devices()
        restarted=PhoneControl(replacement,state_dir=self.directory)
        with self.assertRaises(RequestError) as error: restarted.command(token,'apply',request)
        self.assertEqual(error.exception.status,409);self.assertFalse(self.usb.running)
    def test_lost_control_connection_does_not_end_accepted_session(self):
        control=PhoneControl(self.service,state_dir=self.directory);token=self.pair(control)
        current=self.service.status()
        control.command(token,'apply',dict(deviceId='test-phone',requestId='apply-before-page-close',timestamp=control.clock(),expectedRevision=current['controlRevision'],expectedEpoch=current['controlEpoch'],point=dict(latitude=1,longitude=2)))
        self.usb.event('connected');self.usb.event('video-ready');self.usb.event('subscribed',active=True)
        del control
        self.service.tick()
        self.assertTrue(self.usb.running);self.assertEqual(self.service.status()['helperAcceptedBatches'],1)
        self.service.stop();self.assertFalse(self.usb.running)
    def test_failed_revocation_write_disables_phone_control_and_reports_failure(self):
        control=PhoneControl(self.service,state_dir=self.directory);token=self.pair(control)
        identifier=control.local_status()['grants'][0]['grantId']
        path=self.directory/'grants.json';path.rename(self.directory/'saved-grants.json');path.mkdir()
        with self.assertRaises(ValueError): control.revoke(identifier)
        with self.assertRaises(RequestError): control.status(token)
        self.assertTrue(path.is_dir())
