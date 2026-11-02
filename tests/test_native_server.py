import base64
import hashlib
import http.client
import json
from pathlib import Path
import ssl
import tempfile
import threading
import time
import unittest
from urllib.parse import urlparse,parse_qs
from loc2.native_server import NativeServer
from loc2.phone import PhoneControl
from loc2.session import SessionService
from test_session import USBFixture

class NativeControlTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.backend=USBFixture();self.service=SessionService(self.backend);self.service.refresh_devices()
        self.control=PhoneControl(self.service,state_dir=Path(self.folder.name))
        self.server=NativeServer(('127.0.0.1',0),self.control,'localhost',self.folder.name)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.token=None
    def request(self,path,body=None,origin=False):
        connection=http.client.HTTPSConnection('127.0.0.1',self.server.server_port,context=ssl._create_unverified_context(),timeout=5)
        headers={'Content-Type':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        if origin:headers['Origin']='https://untrusted.invalid'
        connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse();value=json.loads(response.read());connection.close();return response.status,value
    def pair(self):
        self.control.create_pairing()
        url=self.server.local_status()['pairingURL'];encoded=parse_qs(urlparse(url).query)['data'][0]
        invitation=json.loads(base64.urlsafe_b64decode(encoded+'='*((4-len(encoded)%4)%4)))
        actual=ssl.PEM_cert_to_DER_cert((Path(self.folder.name)/'tls/server.cert.pem').read_text())
        self.assertEqual(invitation['fingerprint'],hashlib.sha256(actual).hexdigest())
        code,result=self.request('/v1/pair/request',dict(challenge=invitation['challenge'],pollSecret='f'*64,label='Native iPhone'))
        self.assertEqual(code,200)
        body=dict(requestId=result['requestId'],pollSecret='f'*64)
        self.assertEqual(self.request('/v1/pair/poll',body)[1]['state'],'pending')
        self.control.approve(result['requestId'])
        code,value=self.request('/v1/pair/poll',body);self.assertEqual(code,200);self.token=value['token']
        self.assertEqual(self.request('/v1/pair/poll',body)[0],403)
    def command(self,point=None):
        s=self.request('/v1/status')[1]['status']
        body=dict(deviceId='test-phone',requestId='request_'+str(time.time_ns()),timestamp=time.time(),expectedRevision=s['controlRevision'],expectedEpoch=s['controlEpoch'])
        if point:body['point']=point
        return body
    def test_native_tls_authorization_apply_replay_stop_and_revoke(self):
        self.assertEqual(self.request('/v1/status')[0],401)
        self.pair();body=self.command(dict(latitude=1,longitude=2))
        self.assertEqual(self.request('/v1/apply',body)[0],200)
        self.assertEqual(self.request('/v1/apply',body)[0],409)
        self.assertEqual(self.request('/v1/stop',self.command(),origin=True)[0],403)
        self.assertIsNotNone(self.service.status()['sessionId'])
        self.assertEqual(self.request('/v1/stop',self.command())[0],200)
        self.assertIsNone(self.service.status()['sessionId'])
        self.control.revoke(next(iter(self.control.grants.values()))['grantId'])
        self.assertEqual(self.request('/v1/status')[0],401)
    def test_native_map_points_require_calibration_evidence(self):
        self.pair();point=dict(latitude=1,longitude=2,provider='apple-mapkit-native',inputCRS='WGS84',selectionMethod='search',inputCoordinate=dict(latitude=1,longitude=2),normalizedWGS84=dict(latitude=1,longitude=2))
        self.assertEqual(self.request('/v1/apply',self.command(point))[0],400)
        self.assertIsNone(self.service.status()['sessionId'])
        self.control.maps_config={'native':{'coordinatePolicy':'validated-native','validationEvidence':'synthetic test only'}}
        self.assertTrue(self.request('/v1/status')[1]['nativeMapPointsEnabled'])
        self.assertEqual(self.request('/v1/apply',self.command(point))[0],200)
    def test_usb_status_does_not_request_wifi_credentials(self):
        from loc2.current_network import CurrentNetwork
        requests=[]
        self.backend.current_network=CurrentNetwork(requests.append)
        self.backend.requires_network=False
        self.pair()
        code,value=self.request('/v1/status')
        self.assertEqual(code,200);self.assertTrue(value['networkReady']);self.assertEqual(requests,[])
        self.backend.requires_network=True
        self.request('/v1/status');self.assertEqual(len(requests),1)
    def test_server_identity_persists_across_restart(self):
        other=NativeServer(('127.0.0.1',0),self.control,'localhost',self.folder.name)
        try:self.assertEqual(other.fingerprint,self.server.fingerprint)
        finally:other.server_close()

    def test_idle_tls_client_does_not_block_other_clients(self):
        import socket
        idle=socket.create_connection(('127.0.0.1',self.server.server_port))
        try:
            started=time.monotonic()
            self.assertEqual(self.request('/v1/status')[0],401)
            self.assertLess(time.monotonic()-started,1.5)
        finally:idle.close()

    def test_cable_free_pairing_persists_without_granting_any_target(self):
        self.control.native_pairing=True
        self.backend.devices=[]
        self.pair()
        code,value=self.request('/v1/status')
        self.assertEqual(code,200)
        self.assertFalse(value['targetBound'])
        self.assertIsNone(value['deviceId'])
        self.assertEqual(value['status']['availableDevices'],[])
        self.assertIn('已配对',value['status']['connectionHint'])
        self.backend.devices=['another-phone']
        self.service.refresh_devices()
        self.assertEqual(self.request('/v1/status')[1]['status']['availableDevices'],[])
        for device_id in (None,'another-phone'):
            body=self.command(dict(latitude=1,longitude=2));body['deviceId']=device_id
            self.assertEqual(self.request('/v1/apply',body)[0],403)
            self.assertEqual(self.request('/v1/stop',body)[0],403)
        self.assertFalse(self.backend.running)
        reloaded=PhoneControl(self.service,state_dir=Path(self.folder.name),native_pairing=True)
        self.assertFalse(reloaded.status(self.token)['targetBound'])
        self.assertEqual(reloaded.favorite_list(self.token),{'favorites':[]})
        self.server.control=reloaded
        reloaded.revoke(next(iter(reloaded.grants.values()))['grantId'])
        self.assertEqual(self.request('/v1/status')[0],401)

    def test_wireless_target_can_be_authorized_while_offline(self):
        self.control.native_pairing=True
        self.backend.device_id='wireless-configured-target'
        self.backend.devices=[]
        self.pair()
        code,value=self.request('/v1/status')
        self.assertEqual(code,200)
        self.assertTrue(value['targetBound'])
        self.assertEqual(value['deviceId'],'wireless-configured-target')
        self.assertEqual(value['status']['availableDevices'],[])
        self.backend.devices=['wireless-configured-target']
        self.service.refresh_devices()
        body=self.command(dict(latitude=1,longitude=2));body['deviceId']='wireless-configured-target'
        self.assertEqual(self.request('/v1/apply',body)[0],200)
        self.assertTrue(self.backend.running)

    def test_wireless_target_change_during_approval_is_rejected(self):
        self.control.native_pairing=True
        self.backend.devices=[]
        self.backend.device_id='wireless-original-target'
        challenge=self.control.create_pairing()['challenge']
        code,pending=self.request('/v1/pair/request',dict(challenge=challenge,pollSecret='a'*64,label='iPhone'))
        self.assertEqual(code,200)
        self.backend.device_id='wireless-replacement-target'
        with self.assertRaisesRegex(ValueError,'目标手机已变化'):
            self.control.approve(pending['requestId'])
        self.assertFalse(self.control.grants)

    def test_unbound_invitation_does_not_adopt_newly_connected_device(self):
        self.control.native_pairing=True
        self.backend.devices=[]
        challenge=self.control.create_pairing()['challenge']
        self.backend.devices=['another-phone']
        code,pending=self.request('/v1/pair/request',dict(challenge=challenge,pollSecret='a'*64,label='iPhone'))
        self.assertEqual(code,200)
        self.control.approve(pending['requestId'])
        self.assertIsNone(next(iter(self.control.grants.values()))['deviceId'])
