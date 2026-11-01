import Foundation
import CoreLocation
@main struct PlacesProbe {
    static func main() throws {
        let old = Data(#"{"name":"旧手工点","latitude":30.27,"longitude":120.01,"provider":"manual"}"#.utf8)
        var manual = try JSONDecoder().decode(Point.self,from:old)
        precondition(manual.inputCRS == "WGS84")
        precondition(!manual.canPreview,"Unclassified migrated coordinates must not be drawn on a shifted map")
        manual.countryCode = "CN"
        precondition(manual.canPreview)
        precondition(abs(manual.coordinate.longitude-manual.longitude)>0.001)
        let native = try CoordinateTransform.mapPoint(name:"赛银",coordinate:.init(latitude:30.274659,longitude:120.020772),country:"CN",method:"search")
        let decoded = try JSONDecoder().decode(Point.self,from:JSONEncoder().encode(native))
        precondition(decoded == native && decoded.canPreview)
        precondition(decoded.coordinate.latitude == 30.274659)
        precondition(abs(decoded.location.coordinate.latitude-30.2771763)<0.0002)
        print("PASS: migration metadata, preview gating and native-coordinate round trip")
    }
}
