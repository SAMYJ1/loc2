import datetime as dt
import unittest
from location_lab.session import SessionService

class USBFixture:
    def __init__(self):
        self.devices = ['test-phone']
        self.frames = []
        self.running = False
    def device_ids(self): return list(self.devices)
    def start(self, session, device, emit):
        self.session, self.emit, self.running = session, emit, True
    def send(self, frame): self.frames.append(frame)
    def stop(self): self.running = False
    def event(self, kind, **data): self.emit(self.session, kind, **data)

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.usb = USBFixture()
        self.service = SessionService(self.usb, monotonic=lambda:self.now,
            utcnow=lambda:dt.datetime(2027,1,1,tzinfo=dt.timezone.utc))
        self.service.refresh_devices()
    def test_apply_waits_for_real_subscription_and_does_not_claim_adoption(self):
        result=self.service.apply('test-phone', {'latitude':31.23,'longitude':121.47})
        self.assertEqual(result['state'], 'connecting')
        self.service.tick()
        self.assertEqual(self.usb.frames, [])
        self.usb.event('connected')
        self.usb.event('subscribed',active=True)
        self.service.tick()
        self.assertEqual(self.service.status()['helperAcceptedBatches'],1)
        self.assertIn('3113.8000,N,12128.2000,E',self.usb.frames[0])
        self.assertEqual(self.service.status()['adoption'],'unverified')
    def test_invalid_or_stale_apply_preserves_current_target(self):
        current=self.service.apply('test-phone',{'latitude':1,'longitude':2})
        for point in [{'latitude':float('nan'),'longitude':0},{'latitude':91,'longitude':0},
                      {'latitude':1,'longitude':2,'inputCRS':'unknown'},
                      {'latitude':True,'longitude':0}]:
            with self.assertRaises(ValueError): self.service.apply('test-phone',point)
        with self.assertRaises(ValueError):
            self.service.apply('test-phone',{'latitude':3,'longitude':4},expected_session_id='old')
        self.assertEqual(self.service.status()['target']['latitude'],1)
        self.assertEqual(self.service.status()['sessionId'],current['sessionId'])
    def test_stop_reconnect_and_old_events_cannot_resume_previous_target(self):
        old=self.service.apply('test-phone',{'latitude':1,'longitude':2})['sessionId']
        emit=self.usb.emit
        self.usb.event('connected');self.usb.event('subscribed',active=True);self.service.tick()
        self.service.stop()
        self.assertFalse(self.usb.running)
        self.assertIsNone(self.service.status()['target'])
        self.assertEqual(self.service.status()['recovery'],'pending')
        self.service.refresh_devices();self.now=2;self.service.tick()
        self.assertEqual(len(self.usb.frames),1)
        new=self.service.apply('test-phone',{'latitude':3,'longitude':4})['sessionId']
        self.assertNotEqual(old,new)
        emit(old,'subscribed',active=True);emit(old,'disconnected')
        self.assertEqual(self.service.status()['sessionId'],new)
        self.assertFalse(self.service.status()['subscribed'])
    def test_unplug_sleep_and_transport_failure_clear_session(self):
        for event in ('unplug','sleep','failure','start-failure','send-failure'):
            with self.subTest(event=event):
                self.setUp()
                if event=='start-failure':
                    def fail(*args): raise OSError('private detail must not escape')
                    self.usb.start=fail
                    with self.assertRaises(ValueError): self.service.apply('test-phone',{'latitude':1,'longitude':2})
                else:
                    self.service.apply('test-phone',{'latitude':1,'longitude':2})
                    if event=='unplug': self.usb.devices=[];self.service.refresh_devices()
                    elif event=='sleep': self.service.suspend()
                    elif event=='failure': self.usb.event('failure')
                    else:
                        self.usb.event('connected');self.usb.event('subscribed',active=True)
                        def fail(frame): raise OSError('private detail must not escape')
                        self.usb.send=fail;self.service.tick()
                self.assertIsNone(self.service.status()['sessionId'])
                self.assertIsNone(self.service.status()['target'])
                self.assertFalse(self.usb.running)
    def test_switching_target_resets_adoption_but_not_throttling_or_session(self):
        first=self.service.apply('test-phone',{'latitude':1,'longitude':2})
        self.usb.event('connected');self.usb.event('subscribed',active=True);self.service.tick()
        self.service.confirm_adoption(first['sessionId'])
        second=self.service.apply('test-phone',{'latitude':3,'longitude':4},first['sessionId'])
        self.assertEqual(first['sessionId'],second['sessionId'])
        self.assertEqual(second['adoption'],'unverified')
        self.now=.1;self.service.tick();self.assertEqual(len(self.usb.frames),1)
        self.now=1;self.service.tick();self.assertIn('0300.0000,N,00400.0000,E',self.usb.frames[-1])
        for value in range(2,601): self.now=value;self.service.tick()
        self.assertEqual(self.service.status()['helperAcceptedBatches'],601)
        self.usb.event('subscribed',active=False);self.now=601;self.service.tick()
        self.assertEqual(len(self.usb.frames),601)
        self.usb.event('subscribed',active=True);self.service.tick()
        self.assertEqual(len(self.usb.frames),602)
        self.service.stop();self.service.confirm_recovery()
        self.assertEqual(self.service.status()['recovery'],'user-confirmed')
    def test_clock_gap_invalidates_active_session_instead_of_replaying(self):
        self.service.apply('test-phone',{'latitude':1,'longitude':2})
        self.service.tick();self.now=10;self.service.tick()
        self.assertIsNone(self.service.status()['target'])
    def test_device_change_and_enumeration_failure_do_not_start_wrong_target(self):
        self.service.apply('test-phone',{'latitude':1,'longitude':2})
        self.usb.devices=['other-phone']
        with self.assertRaises(ValueError): self.service.apply('test-phone',{'latitude':3,'longitude':4})
        self.assertIsNone(self.service.status()['sessionId'])
        self.service.apply('other-phone',{'latitude':3,'longitude':4})
        def failed(): raise OSError('private error')
        self.usb.device_ids=failed
        self.service.refresh_devices()
        self.assertIsNone(self.service.status()['sessionId'])
        self.assertFalse(self.usb.running)
    def test_synchronous_failure_during_start_does_not_leave_target(self):
        def start(session,device,emit): emit(session,'failure')
        self.usb.start=start
        with self.assertRaises(ValueError): self.service.apply('test-phone',{'latitude':1,'longitude':2})
        self.assertIsNone(self.service.status()['target'])
