import Foundation
import CoreLocation
@main struct RecoveryProbe {
    static func sample(_ second:Double,accessory:Bool? = false,simulated:Bool? = false) -> LocationEvidence {
        let location = CLLocation(coordinate:.init(latitude:30.2,longitude:120.1),altitude:0,horizontalAccuracy:5,verticalAccuracy:5,timestamp:Date(timeIntervalSince1970:second))
        return LocationEvidence(location:location,accessory:accessory,simulated:simulated)
    }
    static func main() {
        let start = Date(timeIntervalSince1970:100)
        var absent = RecoveryAssessment();absent.start(baseline:nil,at:start)
        absent.advance(to:Date(timeIntervalSince1970:121))
        precondition(absent.phase == .needsConfirmation,"No baseline/fix must not spin forever")
        for second in 122...125 { absent.consume(sample(Double(second)),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(absent.phase == .needsConfirmation,"No baseline cannot prove recovery")
        absent.confirm();precondition(absent.phase == .userConfirmed)
        var normal = RecoveryAssessment();normal.start(baseline:sample(90).location,at:start)
        normal.consume(sample(99),at:Date(timeIntervalSince1970:101));precondition(normal.phase == .waiting)
        normal.consume(sample(101,accessory:true),at:Date(timeIntervalSince1970:101))
        for second in 102...104 { normal.consume(sample(Double(second)),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(normal.phase == .observed)
        var unknown = RecoveryAssessment();unknown.start(baseline:sample(90).location,at:start)
        for second in 101...124 { unknown.consume(sample(Double(second),accessory:nil),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(unknown.phase == .needsConfirmation,"Unknown source must not be coerced to false")
        let target = CLLocation(latitude:30.3,longitude:120.2)
        var returned = RecoveryAssessment();returned.start(baseline:sample(90).location,target:target,at:start)
        for second in 101...106 { returned.consume(sample(Double(second),accessory:nil,simulated:nil),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(returned.phase == .observed,"Fresh stable fixes back at baseline and far from the target can establish recovery without source flags")
        var nearTarget = RecoveryAssessment();nearTarget.start(baseline:sample(90).location,target:sample(90).location,at:start)
        for second in 101...125 { nearTarget.consume(sample(Double(second),accessory:nil,simulated:nil),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(nearTarget.phase == .needsConfirmation,"Overlapping target and baseline cannot establish recovery from coordinates alone")
        var stillAccessory = RecoveryAssessment();stillAccessory.start(baseline:sample(90).location,target:target,at:start)
        for second in 101...125 { stillAccessory.consume(sample(Double(second),accessory:true),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(stillAccessory.phase == .needsConfirmation)
        var withoutBaseline = RecoveryAssessment();withoutBaseline.start(baseline:nil,target:target,at:start)
        for second in 101...104 { withoutBaseline.consume(sample(Double(second)),at:Date(timeIntervalSince1970:Double(second))) }
        precondition(withoutBaseline.phase == .observed,"Explicit native-source fixes away from the old target can recover even after an app restart")
        print("PASS: recovery deadlines, missing baseline, stale sample, accessory source and fresh evidence")
    }
}
