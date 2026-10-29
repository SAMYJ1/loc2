"""HTTP boundary checks; synthetic USB and fake page tokens only."""
import unittest
from test_phone import PhoneTests

class MapTests(unittest.TestCase):
    setUp = PhoneTests.setUp
    request = PhoneTests.request
    pair = PhoneTests.pair
    command = PhoneTests.command

    def test_map_configuration_requires_grant_and_defaults_unverified(self):
        self.assertEqual(self.request('/api/maps-config')[0],401)
        self.pair()
        code,result,_=self.request('/api/maps-config')
        self.assertEqual(code,200)
        self.assertEqual(result,dict(token=None,coordinatePolicy='unverified',canApplyMapPoints=False))

    def test_only_explicit_local_calibration_allows_map_point_and_preserves_provenance(self):
        self.pair()
        point=dict(latitude=31.23,longitude=121.47,provider='apple-mapkit-js',inputCRS='WGS84',inputCoordinate=dict(latitude=31.23,longitude=121.47),normalizedWGS84=dict(latitude=31.23,longitude=121.47),selectionMethod='search')
        self.control.maps_config=dict(token='synthetic.page.token',coordinatePolicy='validated-wgs84',privateKey='never-return-this')
        settings=self.request('/api/maps-config')[1]
        self.assertFalse(settings['canApplyMapPoints'])
        self.assertNotIn('privateKey',settings)
        self.assertEqual(settings['token'],'synthetic.page.token')
        self.assertEqual(self.request('/api/apply',self.command(point=point))[0],400)
        self.assertFalse(self.usb.running)
        self.control.maps_config['validationEvidence']='synthetic fixture calibration; not real-device evidence'
        self.assertTrue(self.request('/api/maps-config')[1]['canApplyMapPoints'])
        code,result,_=self.request('/api/apply',self.command(point=point))
        self.assertEqual(code,200,result)
        self.assertEqual(result['status']['target']['provider'],'apple-mapkit-js')
        self.assertEqual(result['status']['target']['inputCoordinate'],point['inputCoordinate'])
        self.assertEqual(result['status']['target']['selectionMethod'],'search')

    def test_spoofed_normalization_cannot_bypass_local_policy(self):
        self.pair()
        self.control.maps_config=dict(coordinatePolicy='validated-wgs84',validationEvidence='synthetic fixture only')
        point=dict(latitude=1,longitude=2,provider='apple-mapkit-js',inputCRS='unverified-mapkit',inputCoordinate=dict(latitude=1,longitude=2),normalizedWGS84=None,selectionMethod='map-tap')
        self.assertEqual(self.request('/api/apply',self.command(point=point))[0],400)
        point.update(inputCRS='WGS84',normalizedWGS84=dict(latitude=1,longitude=2))
        point['inputCoordinate']['latitude']=3
        self.assertEqual(self.request('/api/apply',self.command(point=point))[0],400)
        self.assertFalse(self.usb.running)
        self.assertEqual(self.request('/api/apply',self.command())[0],200)

    def test_csp_and_assets_allow_only_official_maps_hosts(self):
        import http.client
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request('GET','/')
        response=connection.getresponse();body=response.read().decode();policy=response.getheader('Content-Security-Policy');connection.close()
        self.assertIn('https://cdn.apple-mapkit.com',policy)
        self.assertIn("'wasm-unsafe-eval'",policy)
        self.assertNotIn("'unsafe-eval'",policy)
        self.assertNotIn('{{MAPKIT_NONCE}}',body)
        self.assertEqual(self.request('/maps.js')[0],200)

del PhoneTests
