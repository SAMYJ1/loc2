import http.client
import json
import threading
import time
import unittest
from loc2.session import SessionService
from test_session import USBFixture
from loc2.phone import PhoneControl, PhoneServer

class PhoneTests(unittest.TestCase):
    def setUp(self):
        self.usb=USBFixture();self.service=SessionService(self.usb)
        self.service.refresh_devices()
        self.control=PhoneControl(self.service)
        self.server=PhoneServer(('127.0.0.1',0),self.control,advertised_host='127.0.0.1')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.cookie=None
    def request(self,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        values={'Origin':self.server.origin,'Content-Type':'application/json'}
        if self.cookie: values['Cookie']=self.cookie
        values.update(headers or {})
        connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,values)
        response=connection.getresponse();data=response.read();cookie=response.getheader('Set-Cookie');connection.close()
        try: value=json.loads(data)
        except ValueError: value=data.decode()
        return response.status,value,cookie
    def pair(self):
        challenge=self.control.create_pairing()['challenge']
        code,value,_=self.request('/api/pair/request',{'challenge':challenge,'pollSecret':'a'*64,'label':'Test Safari'})
        self.assertEqual(code,200,value)
        self.control.approve(value['requestId'])
        code,value,cookie=self.request('/api/pair/poll',{'requestId':value['requestId'],'pollSecret':'a'*64})
        self.assertEqual(code,200,value);self.cookie=cookie.split(';',1)[0]
    def test_pairing_requires_mac_approval_before_authorized_status(self):
        self.assertEqual(self.request('/api/status')[0],401)
        challenge=self.control.create_pairing()['challenge']
        code,pending,_=self.request('/api/pair/request',{'challenge':challenge,'pollSecret':'b'*64,'label':'Phone'})
        self.assertEqual(code,200,pending)
        self.assertEqual(self.request('/api/status')[0],401)
        self.assertEqual(self.request('/api/pair/poll',{'requestId':pending['requestId'],'pollSecret':'b'*64})[1]['state'],'pending')
        self.control.approve(pending['requestId'])
        code,result,cookie=self.request('/api/pair/poll',{'requestId':pending['requestId'],'pollSecret':'b'*64})
        self.assertEqual(result['state'],'approved')
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie);self.assertIn('Max-Age=31536000',cookie)
        self.cookie=cookie.split(';',1)[0]
        self.assertEqual(self.request('/api/status')[0],200)
        self.assertFalse(self.usb.running)
    def command(self,**overrides):
        body=dict(deviceId='test-phone',point=dict(latitude=31.23,longitude=121.47),
                  requestId='request-'+str(time.time_ns()),timestamp=time.time(),
                  expectedRevision=self.service.status()['controlRevision'],expectedEpoch=self.service.status()['controlEpoch'])
        body.update(overrides)
        return body
    def test_apply_stop_replay_and_stale_initial_apply_are_controlled(self):
        self.pair()
        stale=self.command()
        self.usb.devices=[];self.service.refresh_devices()
        self.usb.devices=['test-phone'];self.service.refresh_devices()
        self.assertEqual(self.request('/api/apply',stale)[0],409)
        self.assertFalse(self.usb.running)
        accepted=self.command()
        code,result,_=self.request('/api/apply',accepted)
        self.assertEqual(code,200,result)
        self.assertEqual(result['status']['target']['latitude'],31.23)
        self.assertEqual(self.request('/api/apply',accepted)[0],409)
        self.assertEqual(self.request('/api/stop',self.command())[0],200)
        self.assertFalse(self.usb.running)
        self.assertEqual(self.request('/api/apply',accepted)[0],409)
        self.assertFalse(self.usb.running)
    def test_wrong_target_stale_requests_and_cross_origin_cannot_apply(self):
        self.assertEqual(self.request('/api/apply',self.command())[0],401)
        self.pair()
        for changes in [dict(deviceId='other-phone'),dict(timestamp=time.time()-60),dict(timestamp=float('nan'))]:
            self.assertGreaterEqual(self.request('/api/apply',self.command(**changes))[0],400)
        self.assertEqual(self.request('/api/apply',self.command(),{'Origin':'http://evil.invalid'})[0],403)
        self.assertEqual(self.request('/api/status',headers={'Host':'evil.invalid'})[0],403)
        self.assertFalse(self.usb.running)
    def test_one_time_challenge_and_polling_secret_cannot_be_reused(self):
        challenge=self.control.create_pairing()['challenge']
        body=dict(challenge=challenge,pollSecret='c'*64,label='Phone')
        code,result,_=self.request('/api/pair/request',body)
        self.assertEqual(code,200)
        self.assertEqual(self.request('/api/pair/request',body)[0],403)
        self.assertEqual(self.request('/api/pair/poll',dict(requestId=result['requestId'],pollSecret='d'*64))[0],403)
        self.usb.devices=['other-phone']
        with self.assertRaises(ValueError): self.control.approve(result['requestId'])
        self.assertFalse(self.usb.running)
    def test_expired_pairing_and_external_admin_routes_are_rejected(self):
        now=[time.time()];self.control.clock=lambda:now[0]
        challenge=self.control.create_pairing()['challenge'];now[0]+=121
        self.assertEqual(self.request('/api/pair/request',dict(challenge=challenge,pollSecret='e'*64))[0],403)
        self.assertEqual(self.request('/api/pair/approve',{})[0],404)
        self.assertEqual(self.request('/../loc2/phone.py')[0],404)
    def test_bound_controller_cannot_read_another_phone_session(self):
        self.pair()
        self.usb.devices=['other-phone'];self.service.refresh_devices()
        self.service.apply('other-phone',{'latitude':10,'longitude':20})
        code,result,_=self.request('/api/status')
        self.assertEqual(code,403)
        self.assertNotIn('status',result)
        self.service.stop()
        self.usb.devices=['test-phone'];self.service.refresh_devices()
        code,result,_=self.request('/api/status')
        self.assertEqual(code,200)
        self.assertNotEqual(result['status']['deviceId'],'other-phone')
    def test_unsupported_methods_cannot_mutate_session(self):
        self.pair()
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        connection.request('PUT','/api/apply',json.dumps(self.command()),{'Host':self.server.authority,'Origin':self.server.origin,'Content-Type':'application/json','Cookie':self.cookie})
        response=connection.getresponse();response.read();connection.close()
        self.assertEqual(response.status,501)
        self.assertFalse(self.usb.running)
    def test_previous_host_epoch_cannot_execute_delayed_command(self):
        self.pair()
        self.assertEqual(self.request('/api/apply',self.command(expectedEpoch='previous-host'))[0],409)
        self.assertFalse(self.usb.running)

    def test_revoked_cookie_is_cleared_and_browser_cannot_revoke_grants(self):
        self.pair()
        self.assertEqual(self.request('/api/pair/revoke',{})[0],404)
        grant_id=self.control.local_status()['grants'][0]['grantId']
        self.control.revoke(grant_id)
        code,value,cookie=self.request('/api/status')
        self.assertEqual(code,401);self.assertIn('Max-Age=0',cookie)
        self.assertEqual(self.request('/api/apply',self.command())[0],401)
