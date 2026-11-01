import SwiftUI
import MapKit

struct LocationMap: UIViewRepresentable {
    var draft: Point?
    var target: Point?
    var focus: CLLocationCoordinate2D?
    var focusRequest: UUID
    var locationRequest: UUID
    var reduceMotion: Bool
    var select: (CLLocationCoordinate2D) -> Void
    var cancelSelection: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsUserLocation = true
        map.showsCompass = false
        map.pointOfInterestFilter = MKPointOfInterestFilter(including:[.publicTransport,.park,.store,.restaurant])
        let hold = UILongPressGestureRecognizer(target:context.coordinator,action:#selector(Coordinator.longPress(_:)))
        hold.minimumPressDuration = 0.5
        hold.delegate = context.coordinator
        let tap = UITapGestureRecognizer(target:context.coordinator,action:#selector(Coordinator.tap(_:)))
        tap.delegate = context.coordinator
        tap.cancelsTouchesInView = false
        tap.require(toFail:hold)
        map.addGestureRecognizer(hold)
        map.addGestureRecognizer(tap)
        return map
    }
    func updateUIView(_ map: MKMapView,context: Context) {
        let coordinator = context.coordinator
        coordinator.parent = self
        if !samePin(coordinator.draft,draft) || !samePin(coordinator.target,target) {
            coordinator.draft = draft;coordinator.target = target
            map.removeAnnotations(map.annotations.filter { !($0 is MKUserLocation) })
            if let draft,draft.canPreview { map.addAnnotation(SelectionPin(draft,active:false)) }
            if let target,target.canPreview,target.latitude != draft?.latitude || target.longitude != draft?.longitude {
                map.addAnnotation(SelectionPin(target,active:true))
            }
        }
        if coordinator.locationRequest != locationRequest {
            coordinator.locationRequest = locationRequest
            coordinator.needsUserLocation = true
            coordinator.centerOnUser(map)
        }
        if coordinator.focusRequest != focusRequest {
            coordinator.focusRequest = focusRequest
            if let focus {
                coordinator.needsUserLocation = false
                coordinator.focus(map,on:focus)
            }
        }
    }
    private func samePin(_ lhs: Point?,_ rhs: Point?) -> Bool {
        guard let lhs,let rhs else { return lhs == nil && rhs == nil }
        return lhs.name == rhs.name && lhs.canPreview == rhs.canPreview &&
            lhs.coordinate.latitude == rhs.coordinate.latitude && lhs.coordinate.longitude == rhs.coordinate.longitude
    }

    final class SelectionPin: MKPointAnnotation {
        let active: Bool
        init(_ point: Point,active: Bool) {
            self.active = active
            super.init();coordinate = point.coordinate;title = active ? "当前报点目标" : point.name
        }
    }

    final class Coordinator: NSObject,MKMapViewDelegate,UIGestureRecognizerDelegate {
        var parent: LocationMap
        var draft: Point?
        var target: Point?
        var focusRequest: UUID
        var locationRequest: UUID
        var needsUserLocation = true
        init(_ parent: LocationMap) {
            self.parent = parent;focusRequest = parent.focusRequest;locationRequest = parent.locationRequest
        }
        func focus(_ map: MKMapView,on coordinate: CLLocationCoordinate2D) {
            map.setUserTrackingMode(.none,animated:false)
            let region = MKCoordinateRegion(center:coordinate,latitudinalMeters:1200,longitudinalMeters:1200)
            map.setRegion(region,animated:!parent.reduceMotion)
        }
        func centerOnUser(_ map: MKMapView) {
            guard let fix = map.userLocation.location,fix.horizontalAccuracy >= 0 else { return }
            needsUserLocation = false
            focus(map,on:map.userLocation.coordinate)
        }
        func mapView(_ mapView: MKMapView,didUpdate userLocation: MKUserLocation) {
            if needsUserLocation { centerOnUser(mapView) }
        }
        func mapView(_ mapView: MKMapView,regionWillChangeAnimated animated: Bool) {
            if mapView.gestureRecognizers?.contains(where:{ $0.state == .began || $0.state == .changed }) == true {
                needsUserLocation = false
            }
        }
        func mapView(_ mapView: MKMapView,viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let pin = annotation as? SelectionPin else { return nil }
            let view = MKMarkerAnnotationView(annotation:pin,reuseIdentifier:nil)
            view.markerTintColor = pin.active ? .systemOrange : .systemTeal
            view.glyphImage = UIImage(systemName:pin.active ? "location.fill" : "mappin")
            return view
        }
        @objc func longPress(_ gesture: UILongPressGestureRecognizer) {
            guard gesture.state == .began,let map = gesture.view as? MKMapView else { return }
            needsUserLocation = false
            parent.select(map.convert(gesture.location(in:map),toCoordinateFrom:map))
        }
        @objc func tap(_ gesture: UITapGestureRecognizer) {
            if gesture.state == .ended { parent.cancelSelection() }
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,shouldReceive touch: UITouch) -> Bool {
            var view = touch.view
            while let current = view {
                if current is MKAnnotationView || current is UIControl { return false }
                view = current.superview
            }
            return true
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { true }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,shouldRequireFailureOf other: UIGestureRecognizer) -> Bool {
            gestureRecognizer is UITapGestureRecognizer && (other as? UITapGestureRecognizer)?.numberOfTapsRequired == 2
        }
    }
}
