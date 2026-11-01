// GCJ transform adapted from googollee/eviltransform (BSD-3-Clause).
// See third_party/eviltransform/LICENSE. Only selected mainland-China map data is converted.
import Foundation
import CoreLocation

enum CoordinateTransform {
    static func wgsToGCJ(_ c: CLLocationCoordinate2D) -> CLLocationCoordinate2D {
        let x = c.longitude-105, y = c.latitude-35, p = Double.pi
        let d = 20*sin(6*x*p)+20*sin(2*x*p)
        var lat = d+20*sin(y*p)+40*sin(y*p/3)+160*sin(y*p/12)+320*sin(y*p/30)
        var lon = d+20*sin(x*p)+40*sin(x*p/3)+150*sin(x*p/12)+300*sin(x*p/30)
        lat = lat*2/3-100+2*x+3*y+0.2*y*y+0.1*x*y+0.2*sqrt(abs(x))
        lon = lon*2/3+300+x+2*y+0.1*x*x+0.1*x*y+0.1*sqrt(abs(x))
        let rad = c.latitude*p/180, ee = 0.00669342162296594323, radius = 6378137.0
        let magic = 1-ee*sin(rad)*sin(rad), root = sqrt(magic)
        return .init(latitude:c.latitude+lat*180/((radius*(1-ee))/(magic*root)*p),
                     longitude:c.longitude+lon*180/(radius/root*cos(rad)*p))
    }
    static func gcjToWGS(_ c: CLLocationCoordinate2D) -> CLLocationCoordinate2D {
        var result = c
        for _ in 0..<12 {
            let transformed = wgsToGCJ(result)
            let lat = transformed.latitude-c.latitude, lon = transformed.longitude-c.longitude
            result.latitude -= lat;result.longitude -= lon
            if abs(lat)<0.00000001 && abs(lon)<0.00000001 { break }
        }
        return result
    }
    static func mapPoint(name:String,coordinate:CLLocationCoordinate2D,country:String?,method:String) throws -> Point {
        guard let country else { throw AppFailure("无法确认该地点的坐标来源，请重试或输入WGS84坐标") }
        let normalized = country == "CN" ? gcjToWGS(coordinate) : coordinate
        return Point(name:name,latitude:normalized.latitude,longitude:normalized.longitude,provider:"apple-mapkit-native",
                     selectionMethod:method,inputCRS:country == "CN" ? "GCJ-02" : "WGS84",
                     inputLatitude:coordinate.latitude,inputLongitude:coordinate.longitude,countryCode:country)
    }
    static func pointAtTap(_ coordinate:CLLocationCoordinate2D) async throws -> Point {
        let items = try await CLGeocoder().reverseGeocodeLocation(.init(latitude:coordinate.latitude,longitude:coordinate.longitude))
        return try mapPoint(name:items.first?.name ?? "地图选点",coordinate:coordinate,country:items.first?.isoCountryCode,method:"map-tap")
    }
}
