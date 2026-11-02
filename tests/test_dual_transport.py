import unittest
from location_lab.dual_transport import DualTransportBackend
from location_lab.session import SessionService
from location_lab.local_host import dispatch
from location_lab.current_network import CurrentNetwork
from test_session import USBFixture


class WirelessFixture(USBFixture):
    lane='bluetooth'
    device_id='paired-phone'
    current_network=None
    unavailable_reason=None
    def __init__(self,usb):
        super().__init__();self.usb=usb;self.prepared=0;self.available=True
    def device_ids(self):return [self.device_id] if self.available and not self.usb.devices else []
    def prepare_for_apply(self):self.prepared+=1


class DualTransportTests(unittest.TestCase):
    def setUp(self):
        self.usb=USBFixture();self.usb.lane='usb'
        self.wireless=WirelessFixture(self.usb)
        self.backend=DualTransportBackend(self.usb,self.wireless,'test-phone')
        self.service=SessionService(self.backend,monotonic=lambda:0)
        self.addCleanup(self.service.shutdown)
    def apply(self):return self.service.apply('paired-phone',dict(latitude=1,longitude=2))
    def report(self,backend):
        backend.event('connected');backend.event('video-ready');backend.event('subscribed',active=True);self.service.tick()
    def test_usb_preferred_and_does_not_require_wifi_credentials(self):
        self.wireless.available=False
        self.assertEqual(self.service.refresh_devices()['availableDevices'],['paired-phone'])
        self.apply();self.report(self.usb)
        self.assertEqual(len(self.usb.frames),1);self.assertFalse(self.wireless.running)
        self.assertEqual(self.wireless.prepared,0)
    def test_unsupported_wpa3_does_not_block_usb_reporting(self):
        self.backend.current_network=CurrentNetwork(lambda request:self.fail('USB must not request Wi-Fi credentials'))
        self.backend.current_network.update_metadata(dict(ssid='fixture',channel=48,wifiInterface='en0',
            accessPointMAC='00:11:22:33:44:55',wifiSecurity=4))
        self.assertEqual(self.backend.current_network.issue,'unsupported-wpa3')
        self.apply();self.report(self.usb)
        self.assertEqual(len(self.usb.frames),1);self.assertEqual(self.wireless.prepared,0)
        self.assertIsNone(self.service.refresh_devices()['connectionHint'])
    def test_wireless_when_usb_absent(self):
        self.usb.devices=[];self.apply();self.report(self.wireless)
        self.assertEqual(self.wireless.prepared,1);self.assertEqual(len(self.wireless.frames),1)
    def test_usb_insertion_stops_wireless_without_replaying(self):
        self.usb.devices=[];self.apply();self.report(self.wireless)
        old_emit=self.wireless.emit;old_session=self.wireless.session
        self.usb.devices=['test-phone'];s=self.service.refresh_devices()
        self.assertIsNone(s['sessionId']);self.assertIsNone(s['target']);self.assertFalse(self.wireless.running)
        self.service.refresh_devices();self.service.tick();self.assertFalse(self.usb.running)
        self.apply();old_emit(old_session,'video-ready');self.assertFalse(self.service.status()['videoReady'])
        self.report(self.usb);self.assertEqual(len(self.usb.frames),1)
    def test_usb_removal_requires_explicit_apply_for_wireless(self):
        self.apply();self.report(self.usb);self.usb.devices=[]
        self.assertIsNone(self.service.refresh_devices()['sessionId'])
        self.service.refresh_devices();self.service.tick();self.assertFalse(self.wireless.running)
        self.apply();self.report(self.wireless);self.assertEqual(len(self.wireless.frames),1)
    def test_cable_change_before_send_stops_without_sending_on_new_transport(self):
        self.apply()
        self.usb.event('connected');self.usb.event('video-ready');self.usb.event('subscribed',active=True)
        self.usb.devices=[];self.service.tick()
        self.assertEqual(self.service.status()['stopReason'],'transport-changed')
        self.assertEqual(self.usb.frames,[]);self.assertEqual(self.wireless.frames,[])
    def test_unrelated_usb_device_cannot_receive_authorized_phone_target(self):
        self.usb.devices=['different-phone'];self.assertEqual(self.service.refresh_devices()['availableDevices'],[])
        with self.assertRaises(ValueError):self.apply()
        self.assertFalse(self.usb.running)
    def test_failed_usb_start_does_not_silently_fallback(self):
        def fail(*args):raise OSError('fixture failure')
        self.usb.start=fail
        with self.assertRaises(ValueError):self.apply()
        self.assertFalse(self.wireless.running);self.assertIsNone(self.backend.active)
    def test_cable_change_between_preparation_and_start_does_not_fallback(self):
        self.backend.prepare_for_apply();self.usb.devices=[]
        with self.assertRaises(ValueError):self.backend.start('session','paired-phone',lambda *a,**kw:None)
        self.assertFalse(self.usb.running);self.assertFalse(self.wireless.running)
    def test_idle_transport_change_invalidates_old_command_revision(self):
        self.usb.devices=[];old=self.service.refresh_devices()
        self.usb.devices=['test-phone'];new=self.service.refresh_devices()
        self.assertEqual(new['availableDevices'],old['availableDevices'])
        self.assertGreater(new['controlRevision'],old['controlRevision'])
        self.assertEqual(new['transport'],'usb')
    def test_wifi_change_does_not_stop_an_active_usb_session(self):
        meta=dict(ssid='first',channel=36,wifiInterface='en0',accessPointMAC='00:11:22:33:44:55',wifiSecurity=2)
        self.backend.current_network=CurrentNetwork(lambda request:None)
        self.backend.current_network.update_metadata(meta)
        self.apply();self.report(self.usb)
        revision=self.service.status()['controlRevision']
        dispatch(self.service,dict(action='network-status',network=dict(meta,ssid='second')))
        self.assertIsNotNone(self.service.status()['sessionId'])
        self.assertEqual(self.service.status()['controlRevision'],revision)
