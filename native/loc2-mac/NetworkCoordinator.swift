import AppKit
import CoreWLAN
import CoreLocation
import Security

/// Reads the current Wi-Fi and reuses app-owned keychain credentials after initialization.
final class NetworkCoordinator: NSObject, CLLocationManagerDelegate {
    private let location = CLLocationManager()
    private var timer: Timer?
    private var requested: String?
    private var fetching: String?
    private var allowInteraction = false
    private var metadataIssue: String?
    private let credentials = WiFiCredentials(storage:KeychainWiFiStorage())
    var status: (([String:Any]?) -> Void)?
    var completion: ((String,[String:Any]?,String?) -> Void)?
    override init() { super.init();location.delegate = self }
    func start() {
        let tick = Timer(timeInterval:3,repeats:true) { [weak self] _ in self?.poll() }
        RunLoop.main.add(tick,forMode:.common);timer = tick;poll()
    }
    private var authorized: Bool { location.authorizationStatus == .authorizedAlways }
    private func metadata() -> [String:Any]? {
        guard authorized,let wifi = CWWiFiClient.shared().interface(),let ssid = wifi.ssid(),!ssid.isEmpty,
              let channel = wifi.wlanChannel(),let bssid = wifi.bssid(),!bssid.isEmpty else { return nil }
        let mode: Int
        switch wifi.security().rawValue {
        case 2,3,4,5: mode = 2
        case 11: mode = 4
        case 13: mode = 3
        default: metadataIssue = "unsupported-security";return nil
        }
        metadataIssue = nil
        return ["ssid":ssid,"wifiInterface":wifi.interfaceName ?? "en0","channel":channel.channelNumber,
                "accessPointMAC":bssid,"wifiSecurity":mode]
    }
    private func poll() { status?(metadata()) }
    func request(_ identifier: String,interactive:Bool = false) {
        requested = identifier;allowInteraction = interactive
        if location.authorizationStatus == .notDetermined { location.requestWhenInUseAuthorization();return }
        obtain()
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        poll()
        if requested != nil { obtain() }
    }
    private func obtain() {
        guard fetching == nil,let identifier = requested else { return }
        guard let current = metadata(),let ssid = current["ssid"] as? String else {
            requested = nil;completion?(identifier,nil,metadataIssue ?? "metadata:\(location.authorizationStatus.rawValue)");return
        }
        let interactive = allowInteraction
        status?(current);fetching = identifier
        DispatchQueue.global(qos:.userInitiated).async { [weak self] in
            guard let self else { return }
            var result = errSecSuccess
            var password: String?
            let wifi = CWWiFiClient.shared().interface(withName:current["wifiInterface"] as? String ?? "en0")
            let observed = try? wifi?.scanForNetworks(withSSID:Data(ssid.utf8))
            let bssid = current["accessPointMAC"] as? String
            let accessPoint = observed?.first { $0.bssid?.lowercased() == bssid?.lowercased() }
            let transition = accessPoint?.supportsSecurity(.wpa3Transition) == true
            let security = transition ? 3 : (current["wifiSecurity"] as? Int ?? 0)
            let unsupportedWPA3 = security >= 3 && !transition
            if unsupportedWPA3 { result = errSecParam }
            else {
                do { password = try self.credentials.password(for:ssid,interactive:interactive) }
                catch let error as WiFiCredentialFailure { result = error.status }
                catch { result = errSecInternalError }
            }
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.fetching = nil
                let stillCurrent = self.metadata()
                let matches = (stillCurrent?["ssid"] as? String) == ssid &&
                    (stillCurrent?["accessPointMAC"] as? String) == (current["accessPointMAC"] as? String)
                if self.requested == identifier {
                    self.requested = nil
                    if result == errSecSuccess,let password,!password.isEmpty,matches {
                        var value = current;value["password"] = password
                        value["wifiHandshakeSecurity"] = security
                        value["wifiAPSupportsTransition"] = transition
                        self.completion?(identifier,value,nil)
                    } else { self.completion?(identifier,nil,matches ? (unsupportedWPA3 ? "unsupported-wpa3" : "keychain:\(result)") : "network-changed") }
                }
                if self.requested != nil { self.obtain() }
            }
        }
    }
}
