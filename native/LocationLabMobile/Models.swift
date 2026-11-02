import Foundation
import CoreLocation

struct Point: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
    var latitude: Double
    var longitude: Double
    var provider = "apple-mapkit-native"
    var selectionMethod = "map-tap"
    var inputCRS = "WGS84"
    var inputLatitude: Double?
    var inputLongitude: Double?
    var countryCode: String?
    var canPreview: Bool {
        guard ["WGS84","GCJ-02"].contains(inputCRS),countryCode?.count == 2 else { return false }
        return provider != "apple-mapkit-native" || (inputLatitude != nil && inputLongitude != nil)
    }
    var coordinate: CLLocationCoordinate2D {
        if provider == "apple-mapkit-native", let lat = inputLatitude, let lon = inputLongitude { return .init(latitude:lat,longitude:lon) }
        let wgs = CLLocationCoordinate2D(latitude:latitude,longitude:longitude)
        return countryCode == "CN" ? CoordinateTransform.wgsToGCJ(wgs) : wgs
    }
    var location: CLLocation { .init(latitude: latitude, longitude: longitude) }
    var payload: [String: Any] {
        let coordinate: [String: Double] = ["latitude":latitude,"longitude":longitude]
        return ["name":name,"latitude":latitude,"longitude":longitude,"provider":provider,
                "selectionMethod":selectionMethod,"inputCRS":inputCRS,"countryCode":countryCode ?? "",
                "inputCoordinate":["latitude":inputLatitude ?? latitude,"longitude":inputLongitude ?? longitude],"normalizedWGS84":coordinate]
    }
}

struct PlaceLibrary: Codable {
    var favorites: [Point] = []
    var recent: [Point] = []
    var draft: Point?
}

struct ServerProfile: Codable, Equatable, Identifiable, Sendable {
    var endpoint: String
    var fingerprint: String
    var token: String?
    var name: String? = nil
    var id: String { fingerprint.lowercased() }
    var displayName: String {
        if let name,!name.isEmpty { return name }
        let host = URL(string:endpoint)?.host ?? "Mac"
        return host.hasSuffix(".local") ? String(host.dropLast(6)) : host
    }
}

struct Invitation: Decodable {
    let version: Int
    let endpoint: String
    let fingerprint: String
    let challenge: String
    static func parse(_ string: String) throws -> Invitation {
        guard let url = URLComponents(string: string), url.scheme == "locationlab", url.host == "pair",
              var encoded = url.queryItems?.first(where: { $0.name == "data" })?.value else { throw AppFailure("连接邀请格式无效") }
        encoded = encoded.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
        guard encoded.count < 8192, let bytes = Data(base64Encoded: encoded) else { throw AppFailure("连接邀请无效") }
        let value = try JSONDecoder().decode(Invitation.self, from: bytes)
        guard value.version == 1, let endpoint = URLComponents(string:value.endpoint), endpoint.scheme == "https",
              endpoint.host != nil, endpoint.user == nil, endpoint.password == nil,
              endpoint.path.isEmpty, endpoint.query == nil, endpoint.fragment == nil,
              value.fingerprint.count == 64, value.fingerprint.allSatisfy({ $0.isHexDigit }),
              value.challenge.count >= 32 else { throw AppFailure("连接邀请不受支持") }
        return value
    }
}

struct SessionSnapshot {
    var epoch = ""
    var revision = 0
    var sessionID: String?
    var deviceID = ""
    var targetAvailable = false
    var state = "disconnected"
    var target: Point?
    var batches = 0
    var nativeMapPointsEnabled = false
    var error: String?
    var stage: String?
    var connectionHint: String?
    var transport = "unavailable"
    var transportPolicy = "fixed"
    var controlTransport = "network"
    var connectionTitle: String {
        if controlTransport == "usb" && transport == "usb" { return "USB 连接" }
        if controlTransport == "network" && transport == "bluetooth" { return "无线连接" }
        return (controlTransport == "usb" ? "USB 控制 · " : "局域网控制 · ") + transportTitle
    }
    var transportTitle: String {
        switch transport {
        case "usb": return "USB 报点"
        case "bluetooth": return "无线报点"
        default: return "等待报点通道"
        }
    }
    var connected = false
    var subscribed = false
    var videoReady = false
    var decodedFrames = 0
    var recovery = "not-required"
    var sessionStartedAt: Date?
    init() {}
    init(_ value: [String:Any]) {
        deviceID = value["deviceId"] as? String ?? ""
        nativeMapPointsEnabled = value["nativeMapPointsEnabled"] as? Bool ?? false
        let data = value["status"] as? [String:Any] ?? [:]
        targetAvailable = (data["availableDevices"] as? [String] ?? []).contains(deviceID)
        epoch = data["controlEpoch"] as? String ?? ""
        revision = data["controlRevision"] as? Int ?? 0
        sessionID = data["sessionId"] as? String
        state = data["state"] as? String ?? "disconnected"
        batches = data["targetAcceptedBatches"] as? Int ?? 0
        error = data["error"] as? String
        stage = data["diagnosticStage"] as? String
        connectionHint = data["connectionHint"] as? String
        transport = data["transport"] as? String ?? value["transport"] as? String ?? "unavailable"
        transportPolicy = data["transportPolicy"] as? String ?? "fixed"
        controlTransport = value["controlTransport"] as? String ?? "network"
        connected = data["connected"] as? Bool ?? false
        subscribed = data["subscribed"] as? Bool ?? false
        videoReady = data["videoReady"] as? Bool ?? false
        decodedFrames = data["videoDecodedFrames"] as? Int ?? 0
        recovery = data["recovery"] as? String ?? "not-required"
        if let time = data["sessionStartedAt"] as? Double { sessionStartedAt = Date(timeIntervalSince1970:time) }
        if let point = data["target"] as? [String:Any], let lat = point["latitude"] as? Double, let lon = point["longitude"] as? Double {
            let input = point["inputCoordinate"] as? [String:Double]
            target = Point(name: point["name"] as? String ?? "当前目标",latitude:lat,longitude:lon,provider:point["provider"] as? String ?? "manual",
                           inputCRS:point["inputCRS"] as? String ?? "WGS84",inputLatitude:input?["latitude"],inputLongitude:input?["longitude"],countryCode:point["countryCode"] as? String)
        }
    }
    var command: [String:Any] {
        ["deviceId":deviceID,"requestId":UUID().uuidString,"timestamp":Date().timeIntervalSince1970,
         "expectedRevision":revision,"expectedEpoch":epoch]
    }
}

struct AppFailure: LocalizedError {
    let message: String
    var statusCode: Int?
    var identityFailure: Bool
    init(_ message: String,statusCode: Int? = nil,identityFailure: Bool = false) {
        self.message = message;self.statusCode = statusCode;self.identityFailure = identityFailure
    }
    var errorDescription: String? { message }
}


extension Point {
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy:CodingKeys.self)
        id = try values.decodeIfPresent(UUID.self,forKey:.id) ?? UUID()
        name = try values.decode(String.self,forKey:.name)
        latitude = try values.decode(Double.self,forKey:.latitude)
        longitude = try values.decode(Double.self,forKey:.longitude)
        provider = try values.decodeIfPresent(String.self,forKey:.provider) ?? "manual"
        selectionMethod = try values.decodeIfPresent(String.self,forKey:.selectionMethod) ?? "map-tap"
        inputCRS = try values.decodeIfPresent(String.self,forKey:.inputCRS) ?? (provider == "manual" ? "WGS84" : "unverified")
        inputLatitude = try values.decodeIfPresent(Double.self,forKey:.inputLatitude)
        inputLongitude = try values.decodeIfPresent(Double.self,forKey:.inputLongitude)
        countryCode = try values.decodeIfPresent(String.self,forKey:.countryCode)
    }
}
