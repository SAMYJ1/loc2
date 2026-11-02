import unittest
from loc2.coordinates import gcj2wgs_exact,wgs2gcj
from loc2.maps import validate_native_point
from loc2.session import validate_point

class CoordinatesTests(unittest.TestCase):
    def test_measured_saiyin_native_search_matches_independent_wgs_reference(self):
        # 2026-10-30 native MKLocalSearch result; independent reference from prior on-device test.
        lat,lon=gcj2wgs_exact(30.274659,120.020772)
        self.assertLess(abs(lat-30.2771763),.0002)
        self.assertLess(abs(lon-120.0158935),.0002)
    def test_server_rejects_client_normalization_that_uses_raw_map_coordinate(self):
        source=dict(latitude=30.274659,longitude=120.020772)
        point=dict(**source,provider='apple-mapkit-native',countryCode='CN',inputCRS='GCJ-02',selectionMethod='search',inputCoordinate=source,normalizedWGS84=source)
        policy=dict(coordinatePolicy='validated-native',validationEvidence='public reference fixture')
        with self.assertRaises(ValueError):validate_native_point(point,policy)
        lat,lon=gcj2wgs_exact(**{'gcjLat':source['latitude'],'gcjLng':source['longitude']})
        point.update(latitude=lat,longitude=lon,normalizedWGS84=dict(latitude=lat,longitude=lon))
        self.assertEqual(validate_point(validate_native_point(point,policy))['inputCoordinate'],source)
    def test_global_native_points_are_not_shifted(self):
        coordinate=dict(latitude=37.3349,longitude=-122.009)
        point=dict(**coordinate,provider='apple-mapkit-native',countryCode='US',inputCRS='WGS84',selectionMethod='map-tap',inputCoordinate=coordinate,normalizedWGS84=coordinate)
        self.assertEqual(validate_native_point(point,dict(coordinatePolicy='validated-native',validationEvidence='fixture'))['latitude'],coordinate['latitude'])
