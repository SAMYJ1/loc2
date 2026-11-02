import Foundation
import CoreLocation

enum RecoveryPhase: String {
    case idle, waiting, needsConfirmation, observed, userConfirmed
    var title: String {
        switch self {
        case .idle: return "已停止"
        case .waiting: return "等待新定位"
        case .needsConfirmation: return "恢复待确认"
        case .observed: return "已观测恢复"
        case .userConfirmed: return "恢复已确认"
        }
    }
    var detail: String {
        switch self {
        case .idle: return "暂无待确认恢复"
        case .waiting: return "报点已停止，正在等待新的系统定位"
        case .needsConfirmation: return "仍在自动监听新定位；你也可以核对蓝点后手动确认"
        case .observed: return "已连续观测到系统定位恢复，已自动确认"
        case .userConfirmed: return "你已确认蓝点符合实际位置"
        }
    }
}

struct LocationEvidence {
    let location: CLLocation
    let accessory: Bool?
    let simulated: Bool?
    init(_ sample: CLLocation) {
        location = sample
        accessory = sample.sourceInformation?.isProducedByAccessory
        simulated = sample.sourceInformation?.isSimulatedBySoftware
    }
    init(location: CLLocation,accessory: Bool?,simulated: Bool?) {
        self.location = location;self.accessory = accessory;self.simulated = simulated
    }
}

struct RecoveryAssessment {
    private(set) var phase = RecoveryPhase.idle
    private var baseline: CLLocation?
    private var target: CLLocation?
    private var startedAt = Date.distantFuture
    private var lastSample = Date.distantPast
    private var matches = 0
    private var matchingSince: Date?
    private var needsGeographicEvidence = false
    mutating func reset() { self = RecoveryAssessment() }
    mutating func start(baseline: CLLocation?,target: CLLocation? = nil,at time: Date) {
        self.baseline = baseline;self.target = target;startedAt = time;lastSample = .distantPast;matches = 0;matchingSince = nil;needsGeographicEvidence = false;phase = .waiting
    }
    mutating func advance(to now: Date) {
        if phase == .waiting && now.timeIntervalSince(startedAt) >= 20 { phase = .needsConfirmation }
    }
    mutating func consume(_ sample: LocationEvidence,at now: Date) {
        advance(to:now)
        guard phase == .waiting || phase == .needsConfirmation else { return }
        let fix = sample.location
        guard fix.timestamp > startedAt,fix.timestamp > lastSample,now.timeIntervalSince(fix.timestamp) <= 15,
              fix.timestamp.timeIntervalSince(now) < 2,fix.horizontalAccuracy >= 0,fix.horizontalAccuracy <= 100 else { return }
        if fix.timestamp.timeIntervalSince(lastSample)>10 { matches = 0;matchingSince = nil;needsGeographicEvidence = false }
        lastSample = fix.timestamp
        guard sample.accessory != true,sample.simulated != true else { matches = 0;matchingSince = nil;needsGeographicEvidence = false;return }
        let nativeSource = sample.accessory == false && sample.simulated == false
        let nearBaseline = baseline.map {
            $0.timestamp < startedAt && $0.horizontalAccuracy >= 0 && $0.horizontalAccuracy <= 100 &&
            fix.distance(from:$0) <= max(40,fix.horizontalAccuracy+$0.horizontalAccuracy)
        } ?? false
        let awayFromTarget = target.map { fix.distance(from:$0) > max(150,fix.horizontalAccuracy*3) } ?? false
        guard nativeSource ? (nearBaseline || awayFromTarget) : (nearBaseline && awayFromTarget) else { matches = 0;matchingSince = nil;needsGeographicEvidence = false;return }
        if matchingSince == nil { matchingSince = fix.timestamp }
        needsGeographicEvidence = needsGeographicEvidence || !nativeSource
        matches += 1
        if matches >= (needsGeographicEvidence ? 6 : 3),fix.timestamp.timeIntervalSince(matchingSince!) >= (needsGeographicEvidence ? 5 : 2) { phase = .observed }
    }
    mutating func confirm() { phase = .userConfirmed }
    mutating func restore(_ phase: RecoveryPhase) {
        if phase == .observed || phase == .userConfirmed { self.phase = phase }
    }
}
