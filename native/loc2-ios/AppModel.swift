import SwiftUI
import MapKit
import Security

@MainActor final class AppModel: ObservableObject {
    @Published var library = PlaceLibrary()
    @Published var snapshot = SessionSnapshot()
    @Published var profile: ServerProfile?
    @Published private(set) var computers: [ServerProfile] = []
    @Published private(set) var unresolvedComputers: [ServerProfile] = []
    @Published private(set) var discovering = false
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
    private let connector = ComputerConnector()
    private var registry = ComputerRegistry()
    private var registryReadable = true
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
        do {
            registry = try SecureProfile.read();computers = registry.profiles;profile = registry.preferred
            unresolvedComputers = registry.unresolved(excluding:nil)
        } catch { registryReadable = false;notice = "已配对电脑资料无法读取，原记录已保留" }
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
        guard !busy,!computers.isEmpty else { return }
        let generation = commandGeneration
        discovering = true;defer { discovering = false }
        let owner = registry.sessions.first { $0.computerID == profile?.id }?.computerID
        let result = await connector.discover(computers,currentID:profile?.id ?? registry.preferredID,sessionOwnerID:owner)
        guard !Task.isCancelled,generation == commandGeneration,!busy else { result?.client.close();return }
        if let result {
            activate(result)
            let currentGeneration = commandGeneration
            for computer in unresolvedComputers {
                let observed = await connector.connect(computer)
                guard !Task.isCancelled,currentGeneration == commandGeneration,!busy else { observed?.client.close();return }
                if let observed { recordObserved(SessionSnapshot(observed.status),for:computer);observed.client.close() }
            }
        } else {
            online = false;connectionError = "已配对电脑暂不可用，正在自动尝试连接"
            updateSessionWarnings()
        }
    }
    private func resetObservation() {
        snapshot = SessionSnapshot();baseline = nil;lastIdleSample = nil;recoveryTarget = nil
        recovery.reset();recoveryPhase = .idle;recoveryScope = nil;matchCount = 0
        observation = "等待系统新定位"
    }
    private func activate(_ connection: ComputerConnection) {
        if profile?.id != connection.client.profile.id { commandGeneration += 1;resetObservation() }
        client?.close();client = connection.client;profile = connection.client.profile
        online = true;connectionError = nil
        accept(connection.status)
    }
    private func updateSessionWarnings() { unresolvedComputers = registry.unresolved(excluding:online ? profile?.id : nil) }
    private func storeRegistry(_ next: ComputerRegistry) throws {
        guard registryReadable else { throw AppFailure("电脑资料不可安全保存，请先处理原钥匙串记录") }
        try SecureProfile.save(next)
        registry = next;computers = next.profiles;updateSessionWarnings()
    }
    private func recordObserved(_ state: SessionSnapshot,for computer: ServerProfile) {
        guard !state.epoch.isEmpty else { return }
        var next = registry;next.record(state,for:computer)
        if computer.id == profile?.id { next.preferredID = computer.id }
        guard next != registry else { updateSessionWarnings();return }
        do { try storeRegistry(next) }
        catch { registry = next;updateSessionWarnings();notice = "电脑状态暂未保存，重新打开后会再次核对会话" }
    }
    private func accept(_ value: [String:Any]) {
        let previous = snapshot
        var next = SessionSnapshot(value)
        if next.epoch == previous.epoch && next.revision < previous.revision { return }
        if value["nativeMapPointsEnabled"] == nil { next.nativeMapPointsEnabled = previous.nativeMapPointsEnabled }
        let changed = previous.sessionID != next.sessionID || previous.revision != next.revision
        snapshot = next
        if let profile { recordObserved(next,for:profile) }
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
            let canUseLegacyRecovery = profile.map { registry.legacyRecoveryID == $0.id } ?? false
            let storedKey = UserDefaults.standard.string(forKey:recoveryStorageKey("key")) ?? (canUseLegacyRecovery ? UserDefaults.standard.string(forKey:"recovery-key") : nil)
            let storedPhase = UserDefaults.standard.string(forKey:recoveryStorageKey("phase")) ?? (canUseLegacyRecovery ? UserDefaults.standard.string(forKey:"recovery-phase") : nil)
            if storedKey == key,let raw = storedPhase,let phase = RecoveryPhase(rawValue:raw) {
                recovery.restore(phase);syncRecovery()
            } else if next.recovery == "pending" && recoveryScope != key {
                if previous.sessionID == nil { baseline = nil }
                beginRecovery()
            }
        }
    }
    func pair(_ string: String) {
        guard !busy else { return }
        guard registryReadable else { notice = "原电脑资料尚不可读取，请先处理钥匙串状态";return }
        do {
            let invitation = try Invitation.parse(string)
            commandGeneration += 1
            pairingTask?.cancel()
            pairingTask = Task {
                busy = true; pairingMessage = "正在连接 Mac…"
                defer { busy = false }
                let candidate = ServerProfile(endpoint:invitation.endpoint,fingerprint:invitation.fingerprint,token:nil)
                do {
                    let connection = try await connector.pairingConnection(candidate)
                    defer { connection.close() }
                    try Task.checkCancellation()
                    var bytes = [UInt8](repeating:0,count:32)
                    guard SecRandomCopyBytes(kSecRandomDefault,bytes.count,&bytes) == errSecSuccess else { throw AppFailure("无法生成配对请求") }
                    let secret = bytes.map { String(format:"%02x",$0) }.joined()
                    let result = try await connection.request("/v1/pair/request",body:["challenge":invitation.challenge,"pollSecret":secret,"label":"Loc2 · iPhone"])
                    guard let requestID = result["requestId"] as? String else { throw AppFailure("配对请求无效") }
                    pairingMessage = "请在 Mac 菜单栏的配对窗口允许这台 iPhone"
                    for _ in 0..<60 {
                        try await Task.sleep(nanoseconds:2_000_000_000)
                        let value = try await connection.request("/v1/pair/poll",body:["requestId":requestID,"pollSecret":secret])
                        if let token = value["token"] as? String {
                            let paired = ServerProfile(endpoint:candidate.endpoint,fingerprint:candidate.fingerprint,token:token)
                            var next = registry;try next.add(paired);try storeRegistry(next)
                            if snapshot.sessionID == nil && unresolvedComputers.isEmpty {
                                client?.close();client = nil;profile = paired;online = false;resetObservation()
                            }
                            pairingMessage = nil; notice = "已添加 \(paired.displayName)，后续会自动连接可用电脑"
                            busy = false; await refresh(); return
                        }
                    }
                    throw AppFailure("配对等待超时，请在 Mac 重新生成二维码")
                } catch { pairingMessage = nil; notice = error.localizedDescription }
            }
        } catch { notice = error.localizedDescription }
    }
    func forgetComputer(_ computer: ServerProfile) {
        guard !busy else { return }
        do { var next = registry;try next.forget(computer.id);try storeRegistry(next) }
        catch { notice = error.localizedDescription;return }
        commandGeneration += 1
        pairingTask?.cancel(); pairingMessage = nil
        if profile?.id == computer.id {
            client?.close();client = nil;profile = registry.preferred;online = false;resetObservation()
        }
        updateSessionWarnings()
        if foreground { startRefreshing() }
    }
    func renameComputer(_ computer: ServerProfile,name: String) {
        guard !busy else { return }
        let name = String(name.trimmingCharacters(in:.whitespacesAndNewlines).prefix(60))
        guard !name.isEmpty,let index = registry.profiles.firstIndex(where:{ $0.id == computer.id }) else { return }
        do {
            var next = registry;next.profiles[index].name = name;try storeRegistry(next)
            if profile?.id == computer.id { profile = next.profiles[index] }
        } catch { notice = error.localizedDescription }
    }
    func confirmOtherComputersStopped() {
        guard !busy else { return }
        let ids = Set(unresolvedComputers.map(\.id))
        do {
            var next = registry;next.sessions.removeAll { ids.contains($0.computerID) };try storeRegistry(next)
            if !online,let profile,ids.contains(profile.id) { resetObservation() }
        } catch { notice = error.localizedDescription }
    }
    func stopUnresolvedComputers() async {
        guard !busy else { return }
        commandGeneration += 1;busy = true;defer { busy = false }
        for computer in unresolvedComputers {
            guard let connection = await connector.connect(computer) else { continue }
            defer { connection.client.close() }
            do {
                var value = connection.status
                var state = SessionSnapshot(value)
                if state.sessionID != nil {
                    value = try await connection.client.request("/v1/stop",body:state.command)
                    state = SessionSnapshot(value)
                }
                recordObserved(state,for:computer)
                if computer.id == profile?.id { online = true;accept(value) }
            } catch { continue }
        }
        updateSessionWarnings()
        if !unresolvedComputers.isEmpty { notice = "仍有电脑无法联系，请在对应 Mac 上停止报点后确认" }
    }
    func apply() async {
        guard !busy,online,let point = draft,let selected = profile else { notice = "请先连接一台已配对电脑"; return }
        guard unresolvedComputers.isEmpty else { notice = "请先确认上一台电脑已停止报点";return }
        commandGeneration += 1
        busy = true; defer { busy = false }
        var readSucceeded = false
        var sentMutation = false
        do {
            guard let connection = await connector.connect(selected) else { throw AppFailure("当前电脑暂不可用，操作没有转发给其他电脑") }
            defer { connection.client.close() }
            online = true;accept(connection.status);readSucceeded = true
            guard snapshot.targetAvailable else { throw AppFailure("这台电脑的报点通道暂不可用") }
            guard point.provider == "manual" || snapshot.nativeMapPointsEnabled else {
                throw AppFailure("原生地图坐标尚待本机校准。可以先使用明确的 WGS84 坐标。")
            }
            if snapshot.sessionID == nil, let sample = position.latest,
               Date().timeIntervalSince(sample.timestamp) < 10, sample.horizontalAccuracy <= 100,
               sample.sourceInformation?.isProducedByAccessory != true,
               sample.sourceInformation?.isSimulatedBySoftware != true { baseline = sample }
            var body = snapshot.command; body["point"] = point.payload
            var pending = registry;pending.recordPendingApply(for:selected,snapshot:snapshot);try storeRegistry(pending)
            sentMutation = true
            accept(try await connection.client.request("/v1/apply",body:body))
            library.recent.removeAll { $0.latitude == point.latitude && $0.longitude == point.longitude }
            library.recent.insert(point,at:0);library.recent = Array(library.recent.prefix(20));persist()
            notice = nil
        } catch {
            if !readSucceeded || sentMutation { online = false;updateSessionWarnings() }
            notice = error.localizedDescription
        }
    }
    func restore() async {
        guard !busy,let selected = profile else { notice = "无法联系 Mac，请使用 Mac 菜单栏停止"; return }
        commandGeneration += 1
        busy = true; defer { busy = false }
        do {
            guard let connection = await connector.connect(selected) else { throw AppFailure("当前电脑暂不可用") }
            defer { connection.client.close() }
            accept(connection.status)
            if snapshot.sessionID != nil { accept(try await connection.client.request("/v1/stop",body:snapshot.command)) }
            online = true
            if snapshot.recovery == "pending" { if !recoveryWatching && !recoveryConfirmed { beginRecovery() } }
            else { recovery.reset();recoveryPhase = .idle;recoveryScope = nil;observation = "连接已取消，本轮尚未报点" }
            notice = nil
        } catch { online = false;updateSessionWarnings();notice = "尚未确认停止。请重试或在 Mac 菜单栏停止。" }
    }
    private func beginRecovery() {
        recoveryScope = snapshot.epoch + ":" + String(snapshot.revision)
        recovery.start(baseline:baseline,target:recoveryTarget,at:Date());syncRecovery()
    }
    private func syncRecovery() {
        recoveryPhase = recovery.phase
        if recovery.phase != .idle { observation = recovery.phase.detail }
        if recoveryConfirmed {
            UserDefaults.standard.set(snapshot.epoch + ":" + String(snapshot.revision),forKey:recoveryStorageKey("key"))
            UserDefaults.standard.set(recovery.phase.rawValue,forKey:recoveryStorageKey("phase"))
        }
    }
    private func recoveryStorageKey(_ field: String) -> String { "recovery-" + field + "-" + (profile?.id ?? "unpaired") }
    private func observe(_ sample: CLLocation) {
        if online && unresolvedComputers.isEmpty && snapshot.sessionID == nil && !recoveryWatching && sample.horizontalAccuracy >= 0 && sample.horizontalAccuracy <= 100
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
        guard !busy,let selected = profile else { return }
        commandGeneration += 1;busy = true;defer { busy = false }
        do {
            guard let connection = await connector.connect(selected) else { throw AppFailure("当前电脑暂不可用") }
            defer { connection.client.close() }
            let value = try await connection.client.request("/v1/favorites")
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
        if !online { return discovering ? "正在寻找可用 Mac" : "Mac 暂不可达" }
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
