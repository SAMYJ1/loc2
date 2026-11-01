import SwiftUI
import MapKit
import Security

@MainActor final class AppModel: ObservableObject {
    @Published var library = PlaceLibrary()
    @Published var snapshot = SessionSnapshot()
    @Published var profile: ServerProfile?
    @Published var online = false
    @Published var connectionError: String?
    @Published var busy = false
    @Published var notice: String?
    @Published var pairingMessage: String?
    @Published var observation = "等待系统新定位"
    @Published private(set) var recoveryPhase = RecoveryPhase.idle
    var recoveryWatching: Bool { recoveryPhase == .waiting || recoveryPhase == .needsConfirmation }
    var recoveryConfirmed: Bool { recoveryPhase == .observed || recoveryPhase == .userConfirmed }
    let position = PositionObserver()
    private var client: PinnedConnection?
    private var refreshTask: Task<Void,Never>?
    private var pairingTask: Task<Void,Never>?
    private var baseline: CLLocation?
    private var targetObservedAt = Date.distantFuture
    private var recovery = RecoveryAssessment()
    private var lastIdleSample: CLLocation?
    private var recoveryTarget: CLLocation?
    private var matchCount = 0

    private var foreground = false
    private var commandGeneration = 0
    private var recoveryScope: String?
    private let storage: URL
    private var libraryReadable = true
    var draft: Point? { library.draft }

    init() {
        let folder = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0]
        try? FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        storage = folder.appendingPathComponent("places.json")
        if let data = try? Data(contentsOf:storage) {
            do { library = try JSONDecoder().decode(PlaceLibrary.self,from:data) }
            catch { libraryReadable = false;notice = "地点资料无法读取，原文件已保留；暂停保存以免覆盖" }
        }
        profile = SecureProfile.read()
        if let profile { client = PinnedConnection(profile) }
        position.received = { [weak self] location in self?.observe(location) }
        USBControlTunnel.shared.onAvailabilityChange = { [weak self] in
            guard let self,self.foreground,!self.busy else { return }
            self.startRefreshing()
        }
    }
    func persist() {
        guard libraryReadable else { notice = "地点资料无法读取，原文件已保留；暂停保存以免覆盖";return }
        do { try JSONEncoder().encode(library).write(to:storage,options:[.atomic,.completeFileProtectionUntilFirstUserAuthentication]) }
        catch { notice = "地点未能保存，请检查本机储存空间" }
    }
    func select(_ point: Point) { library.draft = point; persist() }
    func cancelSelection() { library.draft = nil;persist() }
    func favorite(_ point: Point) {
        var saved = point
        saved.id = UUID()
        if !library.favorites.contains(where: { $0.name == point.name && $0.latitude == point.latitude && $0.longitude == point.longitude }) {
            library.favorites.append(saved); persist()
        }
    }
    func rename(_ id: UUID, name: String) {
        let name = String(name.trimmingCharacters(in:.whitespacesAndNewlines).prefix(80))
        guard !name.isEmpty, let index = library.favorites.firstIndex(where: { $0.id == id }) else { return }
        library.favorites[index].name = name; persist()
    }
    func setActive(_ active: Bool) {
        foreground = active
        if active { USBControlTunnel.shared.start() } else { USBControlTunnel.shared.stop() }
        position.setActive(active)
        if !active && snapshot.sessionID != nil { matchCount = 0;observation = "返回前台后等待新的系统定位" }
        refreshTask?.cancel()
        guard active else { return }
        startRefreshing()
    }
    private func startRefreshing() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                do { try await Task.sleep(nanoseconds:2_000_000_000) } catch { break }
            }
        }
    }
    func refresh() async {
        recovery.advance(to:Date());syncRecovery()
        if snapshot.sessionID != nil && (position.latest == nil || Date().timeIntervalSince(position.latest!.timestamp)>15) {
            matchCount = 0;observation = "尚未收到新的系统定位，当前采用状态待确认"
        }
        guard !busy, let client, profile?.token != nil else { return }
        let generation = commandGeneration
        do {
            let value = try await client.request("/v1/status")
            guard !Task.isCancelled,generation == commandGeneration else { return }
            accept(value);online = true;connectionError = nil
        } catch {
            guard !Task.isCancelled,generation == commandGeneration else { return }
            online = false;connectionError = error.localizedDescription
        }
    }
    private func accept(_ value: [String:Any]) {
        let previous = snapshot
        var next = SessionSnapshot(value)
        if next.epoch == previous.epoch && next.revision < previous.revision { return }
        if value["nativeMapPointsEnabled"] == nil { next.nativeMapPointsEnabled = previous.nativeMapPointsEnabled }
        let changed = previous.sessionID != next.sessionID || previous.revision != next.revision
        snapshot = next
        if !previous.epoch.isEmpty && next.epoch != previous.epoch { recovery.reset();recoveryPhase = .idle;recoveryScope = nil;baseline = nil;recoveryTarget = nil }
        if changed && next.sessionID != nil {
            recoveryTarget = next.target?.location
            if previous.sessionID == nil,let sample = lastIdleSample,
               sample.timestamp < (next.sessionStartedAt ?? Date()),Date().timeIntervalSince(sample.timestamp) < 30 { baseline = sample }
            targetObservedAt = Date(); matchCount = 0
            observation = "目标已接受，等待系统位置更新"
            recovery.reset(); recoveryPhase = .idle;recoveryScope = nil
        }
        if next.sessionID == nil {
            if previous.sessionID != nil { recoveryTarget = previous.target?.location }
            if next.recovery == "user-confirmed" { recovery.confirm();syncRecovery();return }
            let key = next.epoch + ":" + String(next.revision)
            if UserDefaults.standard.string(forKey:"recovery-key") == key,
               let raw = UserDefaults.standard.string(forKey:"recovery-phase"),let phase = RecoveryPhase(rawValue:raw) {
                recovery.restore(phase);syncRecovery()
            } else if next.recovery == "pending" && recoveryScope != key {
                if previous.sessionID == nil { baseline = nil }
                beginRecovery()
            }
        }
    }
    func pair(_ string: String) {
        guard !busy else { return }
        do {
            let invitation = try Invitation.parse(string)
            commandGeneration += 1
            pairingTask?.cancel()
            pairingTask = Task {
                busy = true; pairingMessage = "正在连接 Mac…"
                defer { busy = false }
                let candidate = ServerProfile(endpoint:invitation.endpoint,fingerprint:invitation.fingerprint,token:nil)
                let connection = PinnedConnection(candidate)
                defer { connection.close() }
                do {
                    var bytes = [UInt8](repeating:0,count:32)
                    guard SecRandomCopyBytes(kSecRandomDefault,bytes.count,&bytes) == errSecSuccess else { throw AppFailure("无法生成配对请求") }
                    let secret = bytes.map { String(format:"%02x",$0) }.joined()
                    let result = try await connection.request("/v1/pair/request",body:["challenge":invitation.challenge,"pollSecret":secret,"label":"toAnywhere · iPhone"])
                    guard let requestID = result["requestId"] as? String else { throw AppFailure("配对请求无效") }
                    pairingMessage = "请在 Mac 菜单栏的配对窗口允许这台 iPhone"
                    for _ in 0..<60 {
                        try await Task.sleep(nanoseconds:2_000_000_000)
                        let value = try await connection.request("/v1/pair/poll",body:["requestId":requestID,"pollSecret":secret])
                        if let token = value["token"] as? String {
                            let paired = ServerProfile(endpoint:candidate.endpoint,fingerprint:candidate.fingerprint,token:token)
                            try SecureProfile.save(paired)
                            client?.close(); client = PinnedConnection(paired); profile = paired
                            pairingMessage = nil; notice = "已连接 Mac，选好目标后点击应用"
                            busy = false; await refresh(); return
                        }
                    }
                    throw AppFailure("配对等待超时，请在 Mac 重新生成二维码")
                } catch { pairingMessage = nil; notice = error.localizedDescription }
            }
        } catch { notice = error.localizedDescription }
    }
    func disconnectController() {
        commandGeneration += 1
        pairingTask?.cancel(); pairingMessage = nil
        client?.close(); client = nil; profile = nil; online = false
        do { try SecureProfile.save(nil) } catch { notice = error.localizedDescription }
        // Disconnecting this controller does not issue a stop or replay any target.
    }
    func apply() async {
        guard !busy, let point = draft, let client else { notice = "先扫码连接 Mac"; return }
        commandGeneration += 1
        busy = true; defer { busy = false }
        do {
            accept(try await client.request("/v1/status")); online = true
            guard point.provider == "manual" || snapshot.nativeMapPointsEnabled else {
                throw AppFailure("原生地图坐标尚待本机校准。可以先使用明确的 WGS84 坐标。")
            }
            if snapshot.sessionID == nil, let sample = position.latest,
               Date().timeIntervalSince(sample.timestamp) < 10, sample.horizontalAccuracy <= 100,
               sample.sourceInformation?.isProducedByAccessory != true,
               sample.sourceInformation?.isSimulatedBySoftware != true { baseline = sample }
            var body = snapshot.command; body["point"] = point.payload
            accept(try await client.request("/v1/apply",body:body))
            library.recent.removeAll { $0.latitude == point.latitude && $0.longitude == point.longitude }
            library.recent.insert(point,at:0);library.recent = Array(library.recent.prefix(20));persist()
            notice = nil
        } catch { notice = error.localizedDescription }
    }
    func restore() async {
        guard !busy, let client else { notice = "无法联系 Mac，请使用 Mac 菜单栏停止"; return }
        commandGeneration += 1
        busy = true; defer { busy = false }
        do {
            accept(try await client.request("/v1/status"))
            accept(try await client.request("/v1/stop",body:snapshot.command))
            online = true
            if snapshot.recovery == "pending" { beginRecovery() }
            else { recovery.reset();recoveryPhase = .idle;recoveryScope = nil;observation = "连接已取消，本轮尚未报点" }
            notice = nil
        } catch { online = false; notice = "尚未确认停止。请重试或在 Mac 菜单栏停止。" }
    }
    private func beginRecovery() {
        recoveryScope = snapshot.epoch + ":" + String(snapshot.revision)
        recovery.start(baseline:baseline,target:recoveryTarget,at:Date());syncRecovery()
    }
    private func syncRecovery() {
        recoveryPhase = recovery.phase
        if recovery.phase != .idle { observation = recovery.phase.detail }
        if recoveryConfirmed {
            UserDefaults.standard.set(snapshot.epoch + ":" + String(snapshot.revision),forKey:"recovery-key")
            UserDefaults.standard.set(recovery.phase.rawValue,forKey:"recovery-phase")
        }
    }
    private func observe(_ sample: CLLocation) {
        if online && snapshot.sessionID == nil && !recoveryWatching && sample.horizontalAccuracy >= 0 && sample.horizontalAccuracy <= 100
            && sample.sourceInformation?.isProducedByAccessory != true && sample.sourceInformation?.isSimulatedBySoftware != true {
            lastIdleSample = sample
        }
        if recoveryWatching {
            recovery.consume(LocationEvidence(sample),at:Date());syncRecovery();return
        }
        guard sample.horizontalAccuracy <= 100 else { observation = "定位精度较低，继续等待";return }
        if let target = snapshot.target,snapshot.batches > 0,sample.timestamp > targetObservedAt {
            let distance = sample.distance(from:target.location)
            if distance <= max(25,min(60,sample.horizontalAccuracy)) { matchCount += 1 } else { matchCount = 0 }
            observation = matchCount >= 3 ? "已观测到目标位置" : "正在报点 · 系统位置距目标约 \(Int(distance)) 米"
        }
    }
    func confirmRecovery() { recovery.confirm();syncRecovery() }
    func importFavorites() async {
        guard let client else { return }
        do {
            let value = try await client.request("/v1/favorites")
            var count = 0
            for item in value["favorites"] as? [[String:Any]] ?? [] {
                guard let point = item["point"] as? [String:Any],let lat = point["latitude"] as? Double,let lon = point["longitude"] as? Double else { continue }
                let name = item["name"] as? String ?? "收藏地点"
                if library.favorites.contains(where: { $0.latitude == lat && $0.longitude == lon && $0.name == name }) { continue }
                let input = point["inputCoordinate"] as? [String:Double]
                var country = point["countryCode"] as? String
                if country == nil && point["inputCRS"] as? String == "WGS84" {
                    country = try? await CLGeocoder().reverseGeocodeLocation(.init(latitude:lat,longitude:lon)).first?.isoCountryCode
                }
                library.favorites.append(Point(name:name,latitude:lat,longitude:lon,provider:point["provider"] as? String ?? "manual",selectionMethod:point["selectionMethod"] as? String ?? "map-tap",inputCRS:point["inputCRS"] as? String ?? "unverified",inputLatitude:input?["latitude"],inputLongitude:input?["longitude"],countryCode:country));count += 1
            }
            persist();notice = "已导入 \(count) 个地点，Mac 原收藏保留"
        } catch { notice = error.localizedDescription }
    }
    var observationText: String {
        if recoveryWatching || recoveryConfirmed { return observation }
        if !online { return "尚未同步 Mac 状态，请检查连接" }
        switch snapshot.state {
        case "connecting":
            return snapshot.stage == "media-preflight-start" ? "正在初始化媒体组件，尚未报点" : "目标已接受，等待\(snapshot.transport == "usb" ? "USB" : "无线")配件连接"
        case "waiting-for-video": return "配件已认证，正在建立定位会话，尚未报点"
        case "waiting-for-subscription": return "会话已连接，等待手机请求位置"
        case "reporting": return observation == "目标已接受，等待系统位置更新" ? "正在报点，等待新的系统位置样本" : observation
        case "error": return snapshot.error ?? "会话已结束，请检查连接"
        default: return observation
        }
    }

    var stateTitle: String {
        if profile == nil { return "未连接 Mac" }
        if !online { return "Mac 暂不可达" }
        if recoveryPhase != .idle { return recoveryPhase.title }
        return ["ready":"连接就绪","disconnected":"等待设备","connecting":"准备定位会话",
                "waiting-for-video":"准备隐藏会话","waiting-for-subscription":"等待位置订阅",
                "reporting":"正在报点","stopped":"已停止","error":"会话已结束"][snapshot.state] ?? "连接就绪"
    }
}

@MainActor final class PlaceSearch: NSObject, ObservableObject, @preconcurrency MKLocalSearchCompleterDelegate {
    @Published var query = "" { didSet { completer.queryFragment = query } }
    @Published var suggestions: [MKLocalSearchCompletion] = []
    @Published var error: String?
    private let completer = MKLocalSearchCompleter()
    override init() { super.init();completer.delegate = self;completer.resultTypes = [.address,.pointOfInterest] }
    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) { suggestions = completer.results }
    func completer(_ completer: MKLocalSearchCompleter,didFailWithError error: Error) { self.error = "搜索暂不可用，请稍后重试" }
    func resolve(_ result: MKLocalSearchCompletion) async throws -> Point {
        let response = try await MKLocalSearch(request:MKLocalSearch.Request(completion:result)).start()
        guard let item = response.mapItems.first else { throw AppFailure("没有找到这个地点") }
        return try CoordinateTransform.mapPoint(name:item.name ?? result.title,coordinate:item.placemark.coordinate,country:item.placemark.isoCountryCode,method:"search")
    }
}
