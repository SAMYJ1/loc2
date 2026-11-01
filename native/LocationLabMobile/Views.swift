import SwiftUI
import MapKit

@main struct LocationLabMobileApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var phase
    var body: some Scene {
        WindowGroup {
            HomeView(model:model)
                .onAppear { model.setActive(true) }
                .onChange(of:phase) { _,value in model.setActive(value == .active) }
                .onOpenURL { model.pair($0.absoluteString) }
        }
    }
}

struct HomeView: View {
    @ObservedObject var model: AppModel
    @ObservedObject private var location: PositionObserver
    @StateObject private var search = PlaceSearch()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var focusedCoordinate: CLLocationCoordinate2D?
    @State private var focusRequest = UUID()
    @State private var locationRequest = UUID()
    @State private var selectionTask: Task<Void,Never>?
    @AppStorage("location-settings-shortcut-configured") private var settingsShortcutConfigured = false
    // Existing installations already imported this name; preserve their shortcut.
    @AppStorage("location-settings-shortcut-name") private var settingsShortcutName = "Location Lab 定位服务"
    @State private var sheet: Panel?
    @FocusState private var searchFocused: Bool
    enum Panel: String,Identifiable { case library,settings,scanner,coordinates,locationSettings; var id:String { rawValue } }
    init(model:AppModel) { self.model = model;location = model.position }
    var body: some View {
        LocationMap(draft:model.draft,target:model.snapshot.target,focus:focusedCoordinate,
                    focusRequest:focusRequest,locationRequest:locationRequest,reduceMotion:reduceMotion,
                    select:{ coordinate in
                        searchFocused = false;selectionTask?.cancel()
                        selectionTask = Task {
                            do {
                                let point = try await CoordinateTransform.pointAtTap(coordinate)
                                guard !Task.isCancelled else { return };model.select(point)
                            } catch { if !Task.isCancelled { model.notice = error.localizedDescription } }
                        }
                    },cancelSelection:clearSelection)
            .ignoresSafeArea()
            .safeAreaInset(edge:.top,spacing:0) { topBar }
            .safeAreaInset(edge:.bottom,spacing:0) { bottomCard }
            .overlay(alignment:.trailing) {
                VStack(spacing:12) {
                    mapButton("我的位置",icon:"location.fill") {
                        location.authorize()
                        clearSelection();locationRequest = UUID()
                    }
                    mapButton("常用地点",icon:"star.fill") { sheet = .library }
                    mapButton("输入坐标",icon:"number") { sheet = .coordinates }
                }.padding(.trailing,18)
            }
            .sheet(item:$sheet) { panel in
                switch panel {
                case .library: LibraryView(model:model,select:{ point in selectionTask?.cancel();model.select(point);if point.canPreview { focus(point.coordinate) };sheet = nil })
                case .settings: SettingsView(model:model,
                    scan:{ sheet = nil;DispatchQueue.main.asyncAfter(deadline:.now()+0.35) { sheet = .scanner } },
                    configureLocationSettings:{ sheet = nil;DispatchQueue.main.asyncAfter(deadline:.now()+0.35) { sheet = .locationSettings } })
                case .locationSettings: locationSettingsSetup
                case .scanner: NavigationStack { QRScanner { code in sheet = nil;model.pair(code) }.ignoresSafeArea(edges:.bottom).navigationTitle("扫描 Mac 二维码").navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement:.cancellationAction) { Button("取消") { sheet = nil } } } }
                case .coordinates: CoordinateView { point in
                    sheet = nil
                    selectionTask?.cancel()
                    selectionTask = Task {
                        var point = point
                        point.countryCode = try? await CLGeocoder().reverseGeocodeLocation(point.location).first?.isoCountryCode
                        guard !Task.isCancelled else { return }
                        model.select(point);if point.canPreview { focus(point.coordinate) }
                    }
                }
                }
            }
            .alert("toAnywhere",isPresented:Binding(get:{ model.notice != nil },set:{ if !$0 { model.notice = nil } })) {
                Button("知道了",role:.cancel) { model.notice = nil }
            } message: { Text(model.notice ?? "") }
            .onDisappear { selectionTask?.cancel() }
            .tint(.teal)
    }
    private var topBar: some View {
        VStack(spacing:8) {
            HStack(spacing:10) {
                Image(systemName:"magnifyingglass").foregroundStyle(.secondary)
                TextField("搜索地点或地址",text:$search.query).focused($searchFocused).submitLabel(.search)
                    .accessibilityIdentifier("place-search")
                if !search.query.isEmpty { Button { search.query = "";searchFocused = false } label:{ Image(systemName:"xmark.circle.fill").foregroundStyle(.secondary) }.accessibilityLabel("清空搜索") }
                Divider().frame(height:22)
                Button { sheet = .settings } label:{ Image(systemName:"slider.horizontal.3").font(.title3) }.accessibilityLabel("连接与设置")
            }.padding(15).background(.regularMaterial,in:RoundedRectangle(cornerRadius:20)).shadow(color:.black.opacity(0.08),radius:12,y:4)
            if searchFocused && !search.query.isEmpty {
                ScrollView {
                    VStack(spacing:0) {
                        ForEach(Array(search.suggestions.prefix(6).enumerated()),id:\.offset) { _,result in
                            Button {
                                searchFocused = false
                                selectionTask?.cancel()
                                selectionTask = Task {
                                    do {
                                        let point = try await search.resolve(result)
                                        guard !Task.isCancelled else { return }
                                        model.select(point);focus(point.coordinate);search.query = ""
                                    } catch { if !Task.isCancelled { model.notice = error.localizedDescription } }
                                }
                            } label: {
                                HStack(spacing:12) {
                                    Image(systemName:"mappin.circle").font(.title2).foregroundStyle(.teal)
                                    VStack(alignment:.leading,spacing:3) { Text(result.title).foregroundStyle(.primary);Text(result.subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
                                    Spacer()
                                }.padding(14).contentShape(Rectangle())
                            }.buttonStyle(.plain)
                            Divider().padding(.leading,48)
                        }
                        if search.suggestions.isEmpty { Text(search.error ?? "正在搜索…").font(.subheadline).foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading).padding() }
                    }.frame(maxWidth:.infinity,alignment:.leading)
                }.frame(maxWidth:.infinity,maxHeight:300).background(.regularMaterial,in:RoundedRectangle(cornerRadius:20))
            }
        }.padding(.horizontal,16).padding(.top,8)
    }
    private var bottomCard: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack {
                Circle().fill(model.online ? Color.teal : Color.secondary).frame(width:7,height:7)
                Text(model.stateTitle).font(.subheadline.weight(.semibold))
                if model.online {
                    Text(model.snapshot.connectionTitle).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                }
                Spacer()
                if model.profile == nil { Button("扫码连接") { sheet = .scanner }.font(.subheadline.weight(.semibold)) }
                else if model.busy { ProgressView().controlSize(.small) }
            }
            if let hint = model.snapshot.connectionHint { Text(hint).font(.caption).foregroundStyle(.orange) }
            if model.snapshot.state == "error",let error = model.snapshot.error { Text(error).font(.caption).foregroundStyle(.orange) }
            if let message = model.pairingMessage { Text(message).font(.subheadline).foregroundStyle(.secondary) }
            if let point = model.draft {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:5) {
                        Text(point.name).font(.title3.weight(.semibold)).lineLimit(2)
                        Text(String(format:"%.6f, %.6f",point.latitude,point.longitude)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        if !point.canPreview { Text("地图预览暂不可用，请核对坐标数值").font(.caption).foregroundStyle(.secondary) }
                    }
                    Spacer()
                    Button { model.favorite(point);model.notice = "已保存到常用地点" } label: { Image(systemName:"star").font(.title2) }.accessibilityLabel("收藏选中地点")
                }
            } else {
                VStack(alignment:.leading,spacing:5) {
                    Text("当前位置").font(.title3.weight(.semibold))
                    Text("蓝点显示系统位置 · 长按选点，轻点地图取消").font(.subheadline).foregroundStyle(.secondary)
                }
            }
            if model.snapshot.sessionID != nil || model.recoveryWatching || model.recoveryConfirmed {
                Text(model.observationText).font(.subheadline).foregroundStyle(model.recoveryConfirmed ? Color.teal : Color.secondary)
                if model.recoveryPhase == .needsConfirmation {
                    Button("手动确认已恢复真实位置") { model.confirmRecovery() }.font(.subheadline.weight(.medium))
                    Text("仍停留在目标时，可在系统设置刷新定位服务后回到这里观察。").font(.caption2).foregroundStyle(.secondary)
                }
            }
            if model.snapshot.sessionID != nil && model.snapshot.batches > 0 {
                VStack(alignment:.leading,spacing:5) {
                    Button { openLocationServices() } label: {
                        Label("打开定位服务设置",systemImage:"location.circle")
                    }.font(.subheadline.weight(.medium)).accessibilityIdentifier("open-location-services")
                        .contextMenu { Button("配置定位服务快捷指令") { sheet = .locationSettings } }
                    Text("隐私与安全性 → 定位服务。手动关闭再开启后，返回这里观察位置。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            HStack(spacing:10) {
                Button { Task { await model.apply() } } label: {
                    Label(model.profile == nil ? "连接后应用" : "应用位置",systemImage:"location.north.fill").frame(maxWidth:.infinity).padding(.vertical,6)
                }.buttonStyle(.borderedProminent).disabled(model.draft == nil || !model.online || model.busy).accessibilityIdentifier("apply-position")
                if model.snapshot.sessionID != nil {
                    Button { Task { await model.restore() } } label:{ Label("恢复",systemImage:"arrow.uturn.backward").padding(.vertical,6) }.buttonStyle(.bordered).disabled(model.busy).accessibilityIdentifier("restore-position")
                }
            }.controlSize(.large)
            if location.permission == .notDetermined { Button("允许读取系统定位，在 App 内观察变化") { location.authorize() }.font(.caption) }
            else if location.permission == .denied { Text("定位权限未开启，仍可选点和管理收藏。可在系统设置中开启定位。").font(.caption).foregroundStyle(.secondary) }
        }.padding(20).background(.regularMaterial,in:RoundedRectangle(cornerRadius:26)).shadow(color:.black.opacity(0.08),radius:16,y:-2).padding(.horizontal,12).padding(.bottom,8)
    }
    private func focus(_ point: CLLocationCoordinate2D) { focusedCoordinate = point;focusRequest = UUID() }
    private func openLocationServices() {
        guard settingsShortcutConfigured else { sheet = .locationSettings;return }
        var destination = URLComponents()
        destination.scheme = "shortcuts";destination.host = "run-shortcut"
        destination.queryItems = [URLQueryItem(name:"name",value:settingsShortcutName)]
        guard let url = destination.url else { return }
        UIApplication.shared.open(url,options:[:]) { opened in
            if !opened { DispatchQueue.main.async { model.notice = "请先安装 Apple 快捷指令 App，并完成定位服务快捷指令的配置。" } }
        }
    }
    private var locationSettingsSetup: some View {
        NavigationStack {
            List {
                Section {
                    Text("这台 iPhone 不允许应用直接跳到全局定位服务。首次添加下面的快捷指令后，按钮会通过快捷指令打开该页面。")
                    Text("它只打开设置页面，定位服务仍由你手动开关。")
                }
                Section("只需配置一次") {
                    Text("1. 导出文件并存储到“文件”App。")
                    if let file = Bundle.main.url(forResource:"toAnywhere 定位服务",withExtension:"shortcut") {
                        ShareLink(item:file) { Label("导出定位服务快捷指令",systemImage:"square.and.arrow.up") }
                    }
                    Text("2. 在“文件”中轻点该文件，添加到快捷指令，保留名称“toAnywhere 定位服务”。")
                    Text("3. 返回这里，点击下方按钮。")
                    Button("已添加，打开定位服务") {
                        settingsShortcutName = "toAnywhere 定位服务"
                        settingsShortcutConfigured = true;sheet = nil;openLocationServices()
                    }
                }
                Section {
                    Text("若快捷指令被删除或改名，长按地图上的设置入口可重新配置。也可手动进入：设置 → 隐私与安全性 → 定位服务。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.navigationTitle("定位服务快捷入口").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement:.cancellationAction) { Button("完成") { sheet = nil } } }
        }
    }
    private func clearSelection() { selectionTask?.cancel();selectionTask = nil;searchFocused = false;model.cancelSelection() }
    private func mapButton(_ title:String,icon:String,action:@escaping ()->Void) -> some View {
        Button(action:action) { Image(systemName:icon).font(.system(size:18,weight:.medium)).frame(width:46,height:46).background(.regularMaterial,in:Circle()).shadow(color:.black.opacity(0.08),radius:8,y:2) }.accessibilityLabel(title)
    }
}

struct LibraryView: View {
    @ObservedObject var model: AppModel
    let select: (Point) -> Void
    @State private var renameID: UUID?
    @State private var newName = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                Section("常用地点") {
                    if model.library.favorites.isEmpty { Text("在地图上选好地点，点星标即可收藏").foregroundStyle(.secondary) }
                    ForEach(model.library.favorites) { point in
                        Button { select(point) } label:{ Label(point.name,systemImage:"star.fill").foregroundStyle(.primary) }
                            .contextMenu { Button("改名") { renameID = point.id;newName = point.name };Button("删除",role:.destructive) { model.library.favorites.removeAll { $0.id == point.id };model.persist() } }
                    }.onDelete { model.library.favorites.remove(atOffsets:$0);model.persist() }.onMove { model.library.favorites.move(fromOffsets:$0,toOffset:$1);model.persist() }
                }
                Section("最近使用") {
                    if model.library.recent.isEmpty { Text("应用过的目标会显示在这里").foregroundStyle(.secondary) }
                    ForEach(model.library.recent) { point in Button { select(point) } label:{ Label(point.name,systemImage:"clock").foregroundStyle(.primary) } }
                    if !model.library.recent.isEmpty { Button("清空最近使用",role:.destructive) { model.library.recent = [];model.persist() } }
                }
            }.navigationTitle("地点").toolbar { ToolbarItem(placement:.cancellationAction) { Button("完成") { dismiss() } };ToolbarItem(placement:.primaryAction) { EditButton() } }
            .alert("地点名称",isPresented:Binding(get:{renameID != nil},set:{if !$0 {renameID = nil}})) {
                TextField("名称",text:$newName)
                Button("保存") { if let id = renameID { model.rename(id,name:newName) };renameID = nil }
                Button("取消",role:.cancel) { renameID = nil }
            }
        }
    }
}

struct SettingsView: View {
    @ObservedObject var model:AppModel
    let scan: ()->Void
    let configureLocationSettings: ()->Void
    @State private var invitation = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                Section("Mac 连接") {
                    LabeledContent("状态",value:model.stateTitle)
                    if let error = model.connectionError { Text(error).font(.caption).foregroundStyle(.secondary) }
                    if let profile = model.profile { Text(URL(string:profile.endpoint)?.host ?? "已授权 Mac").foregroundStyle(.secondary) }
                    Button("扫描 Mac 二维码",systemImage:"qrcode.viewfinder",action:scan)
                    TextField("粘贴连接邀请",text:$invitation).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button("使用连接邀请") { model.pair(invitation);invitation = "";dismiss() }.disabled(invitation.isEmpty)
                    if model.profile != nil { Button("忘记此 Mac",role:.destructive) { model.disconnectController() };Text("忘记连接不会停止 Mac 上的现有会话。需要停止时请先点恢复，或使用 Mac 菜单栏。").font(.caption).foregroundStyle(.secondary) }
                }
                Section("地点") {
                    Button("导入 Mac 现有收藏") { Task { await model.importFavorites() } }.disabled(!model.online)
                    Text("地点保存在这台手机。选择收藏只准备草稿，不会直接应用。").font(.caption).foregroundStyle(.secondary)
                }
                Section("定位观测") {
                    Text("系统蓝点来自本 App 收到的位置样本。它可能已经是所提供的目标位置，不是另一份独立 GPS 真值。").font(.caption)
                    Button("配置定位服务快捷入口",action:configureLocationSettings)
                    Button("打开应用系统设置") { if let url = URL(string:UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }
                    NavigationLink("诊断信息") { DiagnosticView(model:model,location:model.position) }
                }
                Section("许可") {
                    NavigationLink("开源许可") {
                        ScrollView { Text(Bundle.main.url(forResource:"ThirdPartyNotices",withExtension:"txt").flatMap { try? String(contentsOf:$0) } ?? "许可文件不可用").font(.caption).padding() }.navigationTitle("开源许可")
                    }
                }
                Section("个人开发版本") {
                    LabeledContent("签名到期",value:SigningInfo.expiryText)
                    NavigationLink("如何更新与续签") {
                        ScrollView {
                            VStack(alignment:.leading,spacing:18) {
                                Text("1. 先恢复位置，保持手机解锁，并与 Mac 连接同一网络。")
                                Text("2. 在 Mac 的 toAnywhere 菜单栏选择“更新手机 App”。")
                                Text("3. 若 Xcode 要求登录或确认，请在 Mac 本机完成。")
                                Text("4. 更新会覆盖安装并保留收藏和连接授权，不需要先删除 App。")
                                Text("有效期以实际签名为准；更新不一定在尚未到期时立即延长有效期。Mac 菜单栏的停止入口不依赖手机签名。").font(.caption).foregroundStyle(.secondary)
                            }.padding()
                        }.navigationTitle("更新与续签")
                    }
                }
            }.navigationTitle("设置").toolbar { ToolbarItem(placement:.confirmationAction) { Button("完成") { dismiss() } } }
        }
    }
}
struct DiagnosticView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var location: PositionObserver
    var body: some View {
        Form {
            LabeledContent("会话",value:model.snapshot.state)
            LabeledContent("手机控制",value:model.snapshot.controlTransport == "usb" ? "USB" : "局域网")
            LabeledContent("报点通道",value:model.snapshot.transportTitle)
            LabeledContent("已接受批次",value:String(model.snapshot.batches))
            LabeledContent("认证",value:model.snapshot.connected ? "通过" : "等待")
            LabeledContent("位置订阅",value:model.snapshot.subscribed ? "正在请求" : "等待")
            LabeledContent("视频就绪",value:model.snapshot.videoReady ? "是" : "等待")
            LabeledContent("解码帧",value:String(model.snapshot.decodedFrames))
            LabeledContent("阶段",value:model.snapshot.stage ?? "—")
            LabeledContent("原生地图校准",value:model.snapshot.nativeMapPointsEnabled ? "已配置" : "待验证")
            if let sample = location.latest {
                LabeledContent("样本时间",value:sample.timestamp.formatted(date:.omitted,time:.standard))
                LabeledContent("水平精度",value:String(format:"%.1f 米",sample.horizontalAccuracy))
                LabeledContent("外设来源",value:sample.sourceInformation.map { $0.isProducedByAccessory ? "是" : "否" } ?? "未知")
                LabeledContent("软件模拟",value:sample.sourceInformation.map { $0.isSimulatedBySoftware ? "是" : "否" } ?? "未知")
            }
            Text("发送计数不代表手机采用；来源字段缺失也不等于非外设来源。").font(.caption)
        }.navigationTitle("诊断")
    }
}
struct CoordinateView: View {
    let select:(Point)->Void
    @State private var name = ""
    @State private var latitude = ""
    @State private var longitude = ""
    @Environment(\.dismiss) private var dismiss
    private var point: Point? {
        guard let lat = Double(latitude),let lon = Double(longitude),lat.isFinite,lon.isFinite,abs(lat)<=90,abs(lon)<=180 else { return nil }
        return Point(name:name.isEmpty ? "坐标选点" : name,latitude:lat,longitude:lon,provider:"manual")
    }
    var body: some View {
        NavigationStack {
            Form { Section("WGS84 坐标") { TextField("名称（可选）",text:$name);TextField("纬度",text:$latitude).keyboardType(.numbersAndPunctuation);TextField("经度",text:$longitude).keyboardType(.numbersAndPunctuation) };Text("仅输入明确为 WGS84 的坐标，避免将其它地图的偏移坐标直接用于报点。").font(.caption).foregroundStyle(.secondary) }
            .navigationTitle("输入坐标").toolbar { ToolbarItem(placement:.cancellationAction) { Button("取消") { dismiss() } };ToolbarItem(placement:.confirmationAction) { Button("选取") { if let point { select(point) } }.disabled(point == nil) } }
        }
    }
}
