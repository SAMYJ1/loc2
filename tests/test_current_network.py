import unittest
from loc2.current_network import CurrentNetwork
from loc2.session import SessionService
from test_session import USBFixture

class CurrentNetworkTests(unittest.TestCase):
    def setUp(self):
        self.requests=[];self.now=0
        self.network=CurrentNetwork(self.requests.append,clock=lambda:self.now)
        self.meta=dict(ssid='CurrentNetwork',channel=48,wifiInterface='en0',accessPointMAC='00:11:22:33:44:55',wifiSecurity=2)
    def ready(self):
        self.network.update_metadata(self.meta);self.network.prepare()
        self.assertTrue(self.network.complete(self.requests[-1]['requestId'],dict(self.meta,password='test-only')))
    def test_only_current_metadata_can_complete_credential_request(self):
        self.network.update_metadata(self.meta);self.network.prepare();old=self.requests[-1]['requestId']
        other=dict(self.meta,ssid='NewNetwork');self.assertTrue(self.network.update_metadata(other))
        self.assertFalse(self.network.complete(old,dict(self.meta,password='old-only')))
        self.network.prepare();self.assertTrue(self.network.complete(self.requests[-1]['requestId'],dict(other,password='new-only')))
        self.assertEqual(self.network.settings()['ssid'],'NewNetwork')
    def test_system_denial_does_not_reprompt_on_status_poll(self):
        self.network.update_metadata(self.meta);self.network.prepare();request=self.requests[-1]['requestId']
        self.network.complete(request,None,error=True)
        for _ in range(10):self.network.prepare()
        self.assertEqual(len(self.requests),1)
        self.network.prepare(force=True);self.assertEqual(len(self.requests),2)
    def test_stale_network_requires_fresh_system_observation(self):
        self.ready();self.assertTrue(self.network.ready)
        self.now=13;self.assertFalse(self.network.ready)
        self.network.update_metadata(self.meta);self.assertTrue(self.network.ready)
    def test_pending_network_does_not_accept_target_or_start_receiver(self):
        backend=USBFixture();service=SessionService(backend)
        def prepare():
            if not self.network.prepare():raise ValueError('等待当前网络授权')
        backend.prepare_for_apply=prepare
        with self.assertRaises(ValueError):service.apply('test-phone',dict(latitude=1,longitude=2))
        self.assertIsNone(service.status()['sessionId']);self.assertIsNone(service.status()['target']);self.assertFalse(backend.running)
    def test_password_does_not_appear_in_metadata(self):
        self.ready();self.assertNotIn('password',self.network.metadata)
        self.assertNotIn('test-only',self.network.hint or '')

    def test_explicit_refresh_reloads_a_previously_initialized_network(self):
        self.ready()
        self.assertFalse(self.network.prepare(force=True,interactive=True))
        self.assertEqual(len(self.requests),2)
        self.assertTrue(self.requests[-1]['interactive'])
        self.assertTrue(self.network.complete(self.requests[-1]['requestId'],dict(self.meta,password='updated-fixture')))
        self.assertEqual(self.network.settings()['password'],'updated-fixture')

    def test_access_point_roam_invalidates_parameters_without_ending_session(self):
        self.ready()
        self.assertFalse(self.network.update_metadata(dict(self.meta,channel=36,accessPointMAC='00:11:22:33:44:66')))
        self.assertFalse(self.network.ready)
        self.assertTrue(self.network.update_metadata(dict(self.meta,ssid='DifferentSSID')))

    def test_wpa3_is_rejected_before_accepting_a_target_or_starting_receiver(self):
        from unittest.mock import patch
        from loc2.wireless import WirelessBackend
        self.ready()
        wpa3=dict(self.meta,wifiSecurity=4)
        self.network.update_metadata(wpa3);self.network.prepare()
        if self.network.pending:
            self.network.complete(self.requests[-1]['requestId'],dict(wpa3,password='test-only'))
        # A metadata refresh must not reuse previously accepted WPA2 credentials.
        backend=WirelessBackend(None,current_network=self.network,target_bluetooth='00:11:22:33:44:55',
                                enumerate_devices=lambda:[],address=lambda _: '192.168.1.2')
        service=SessionService(backend)
        with patch.object(backend,'start') as start:
            with self.assertRaisesRegex(ValueError,'WPA3'):
                service.apply(backend.device_id,dict(latitude=1,longitude=2))
            start.assert_not_called()
        self.assertIsNone(service.status()['sessionId']);self.assertIsNone(service.status()['target'])
        self.assertEqual(self.network.issue,'unsupported-wpa3')
        self.assertIn('USB',self.network.hint)
        self.assertFalse(self.network.prepare(force=True,interactive=True))
        self.assertEqual(len(self.requests),1)
        # Returning to a supported network restores preparation without a restart.
        self.network.update_metadata(self.meta);self.network.prepare()
        self.assertTrue(self.network.complete(self.requests[-1]['requestId'],dict(self.meta,password='test-only')))
        self.assertTrue(self.network.ready)

    def test_wpa3_transition_also_blocks_the_legacy_wifi_sharing_crash(self):
        self.network.update_metadata(dict(self.meta,wifiSecurity=3))
        self.assertFalse(self.network.prepare(force=True))
        self.assertEqual(self.requests,[])
        self.assertEqual(self.network.issue,'unsupported-wpa3')

    def test_verified_transition_runtime_requires_actual_ap_transition_evidence(self):
        self.network=CurrentNetwork(self.requests.append,clock=lambda:self.now,allow_wpa3_transition=True)
        meta=dict(self.meta,wifiSecurity=4)
        self.network.update_metadata(meta);self.network.prepare()
        response=dict(meta,password='test-only',wifiHandshakeSecurity=3,wifiAPSupportsTransition=True)
        self.assertTrue(self.network.complete(self.requests[-1]['requestId'],response))
        self.assertEqual(self.network.settings()['wifiHandshakeSecurity'],3)
        self.assertEqual(self.network.metadata['wifiSecurity'],4)
        self.network.update_metadata(self.meta);self.network.prepare()
        self.assertTrue(self.network.complete(self.requests[-1]['requestId'],dict(self.meta,
            password='test-only',wifiHandshakeSecurity=3,wifiAPSupportsTransition=True)))
        self.assertEqual(self.network.settings()['wifiHandshakeSecurity'],3)
        self.network.update_metadata(meta);self.network.prepare()
        self.assertFalse(self.network.complete(self.requests[-1]['requestId'],dict(response,wifiAPSupportsTransition=False)))
        self.assertFalse(self.network.ready)
        self.assertEqual(self.network.issue,'unsupported-wpa3')

    def test_pure_wpa3_cannot_be_relabelled_as_wpa2(self):
        self.network=CurrentNetwork(self.requests.append,allow_wpa3_transition=True)
        meta=dict(self.meta,wifiSecurity=4)
        self.network.update_metadata(meta);self.network.prepare()
        self.assertFalse(self.network.complete(self.requests[-1]['requestId'],dict(meta,
            password='test-only',wifiHandshakeSecurity=2,wifiAPSupportsTransition=False)))
        self.assertFalse(self.network.ready)
