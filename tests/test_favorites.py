"""Favorites through authenticated HTTP; the USB backend remains a fixture."""
import tempfile
from pathlib import Path
import unittest
import test_phone
from loc2.phone import PhoneControl

class FavoritesTests(unittest.TestCase):
    request=test_phone.PhoneTests.request
    pair=test_phone.PhoneTests.pair
    command=test_phone.PhoneTests.command
    def setUp(self):
        test_phone.PhoneTests.setUp(self)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state_dir=Path(self.temp.name)
        self.control=PhoneControl(self.service,state_dir=self.state_dir)
        self.control.origin=self.server.origin;self.server.control=self.control

    def test_saved_favorite_survives_new_store_and_preserves_metadata(self):
        self.pair()
        point=dict(latitude=31.23,longitude=121.47,inputCRS='WGS84',provider='manual',
                   inputCoordinate=dict(latitude=31.23,longitude=121.47),normalizedWGS84=dict(latitude=31.23,longitude=121.47))
        code,result,_=self.request('/api/favorites/add',self.command(name='常用地点',point=point))
        self.assertEqual(code,200,result)
        favorite=result['favorites'][0]
        self.assertEqual(favorite['point'],point)
        self.assertIsNone(self.service.status()['target'])
        self.control=PhoneControl(self.service,state_dir=self.state_dir)
        self.control.origin=self.server.origin;self.server.control=self.control
        self.cookie=None;self.pair()
        code,result,_=self.request('/api/favorites')
        self.assertEqual(code,200,result)
        self.assertEqual(result['favorites'],[favorite])
        code,result,_=self.request('/api/favorites/remove',self.command(favoriteId=favorite['id']))
        self.assertEqual(code,200,result)
        self.assertEqual(result['favorites'],[])
    def test_favorites_require_authorization_and_do_not_cross_device_grants(self):
        self.assertEqual(self.request('/api/favorites')[0],401)
        self.assertEqual(self.request('/api/favorites/add',self.command(name='Point',point={}))[0],401)
        self.pair()
        point=dict(latitude=1,longitude=2,provider='manual',inputCRS='WGS84',inputCoordinate=dict(latitude=1,longitude=2),normalizedWGS84=dict(latitude=1,longitude=2))
        body=self.command(name='Point',point=point)
        code,result,_=self.request('/api/favorites/add',body)
        self.assertEqual(code,200,result)
        self.assertEqual(self.request('/api/favorites/add',body)[0],409)
        self.assertEqual(len(self.request('/api/favorites')[1]['favorites']),1)
        favorite_id=result['favorites'][0]['id']
        self.usb.devices=['other-phone'];self.service.refresh_devices()
        self.cookie=None;self.pair()
        self.assertEqual(self.request('/api/favorites')[1]['favorites'],[])
        self.assertEqual(self.request('/api/favorites/remove',self.command(deviceId='other-phone',favoriteId=favorite_id))[0],400)
        self.assertFalse(self.usb.running)

    def test_uncalibrated_map_draft_is_preserved_without_claiming_wgs84(self):
        self.pair()
        point=dict(latitude=31.23,longitude=121.47,provider='apple-mapkit-js',inputCRS='unverified-mapkit',selectionMethod='map-tap',inputCoordinate=dict(latitude=31.23,longitude=121.47),normalizedWGS84=None)
        code,result,_=self.request('/api/favorites/add',self.command(name='待校准地图点',point=point))
        self.assertEqual(code,200,result)
        self.assertEqual(result['favorites'][0]['point'],point)
        self.assertIsNone(self.service.status()['target'])
        self.assertEqual(self.request('/api/apply',self.command(point=point))[0],400)
        self.assertFalse(self.usb.running)
        invalid=dict(point,inputCRS='WGS84')
        self.assertEqual(self.request('/api/favorites/add',self.command(name='错误元数据',point=invalid))[0],400)
    def test_corrupt_or_linked_store_is_not_replaced_silently(self):
        path=self.state_dir/'favorites.json'
        path.write_text('{invalid-json')
        with self.assertRaisesRegex(ValueError,'收藏文件无法读取'):
            PhoneControl(self.service,state_dir=self.state_dir)
        self.assertEqual(path.read_text(),'{invalid-json')
        path.unlink();target=self.state_dir/'missing-target';path.symlink_to(target)
        with self.assertRaisesRegex(ValueError,'收藏文件无法读取'):
            PhoneControl(self.service,state_dir=self.state_dir)
        self.assertTrue(path.is_symlink())
    def test_failed_save_does_not_report_a_new_favorite(self):
        self.pair()
        point=dict(latitude=1,longitude=2,provider='manual',inputCRS='WGS84',inputCoordinate=dict(latitude=1,longitude=2),normalizedWGS84=dict(latitude=1,longitude=2))
        code,result,_=self.request('/api/favorites/add',self.command(name='已保存',point=point))
        self.assertEqual(code,200)
        before=result['favorites']
        path=self.state_dir/'favorites.json'
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        path.unlink();path.mkdir()
        code,result,_=self.request('/api/favorites/add',self.command(name='未保存',point=point))
        self.assertEqual(code,400)
        self.assertIn('Mac 收藏无法保存',result['error'])
        self.assertEqual(self.request('/api/favorites')[1]['favorites'],before)
        self.assertIsNone(self.service.status()['target'])
