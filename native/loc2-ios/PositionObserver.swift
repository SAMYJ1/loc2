import Foundation
import CoreLocation

@MainActor final class PositionObserver: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published var latest: CLLocation?
    @Published var permission = CLAuthorizationStatus.notDetermined
    @Published var message: String?
    private let manager = CLLocationManager()
    private var active = false
    var received: ((CLLocation) -> Void)?
    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
        manager.pausesLocationUpdatesAutomatically = false
        permission = manager.authorizationStatus
    }
    func setActive(_ active: Bool) {
        self.active = active
        if active && (permission == .authorizedWhenInUse || permission == .authorizedAlways) { manager.startUpdatingLocation() }
        else { manager.stopUpdatingLocation() }
    }
    func authorize() {
        if permission == .notDetermined { manager.requestWhenInUseAuthorization() }
        else { setActive(true) }
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        permission = manager.authorizationStatus
        setActive(active)
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let sample = locations.last, sample.horizontalAccuracy >= 0,
              sample.timestamp.timeIntervalSinceNow > -15, sample.timestamp.timeIntervalSinceNow < 2,
              latest == nil || sample.timestamp > latest!.timestamp else { return }
        latest = sample
        message = nil
        received?(sample)
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        message = "暂未取得新的系统定位"
    }
}
