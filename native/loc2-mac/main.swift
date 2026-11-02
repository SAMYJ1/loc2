import ServiceManagement
import AppKit
import Foundation
import CoreImage
import Darwin

final class LocationApp: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
    private var menuBarIcon: MenuBarStatusIcon?
    private var statusMenuController: MenuBarStatusMenu?
    private let menuStatus = NSMenuItem(title:"Loc2 · 正在启动",action:nil,keyEquivalent:"")
    private var window: NSWindow!
    private var pairingWindow: NSWindow!
    private let statusText = NSTextField(wrappingLabelWithString: "正在启动本机会话服务…")
    private let latitude = NSTextField(string: "")
    private let longitude = NSTextField(string: "")
    private let targetText = NSTextField(wrappingLabelWithString: "未应用目标位置")
    private var process: Process?
    private var input: FileHandle?
    private var outputBuffer = Data()
    private var state: [String: Any] = [:]
    private var timer: Timer?
    private var terminating = false
    private let phoneText = NSTextField(wrappingLabelWithString: "手机控制尚未配置")
    private let qrImage = NSImageView()
    private let pendingRequests = NSPopUpButton()
    private let authorizedControllers = NSPopUpButton()
    private var grants: [[String:Any]] = []
    private var phone: [String:Any] = [:]
    private var pending: [[String:Any]] = []
    private var lastPairingURL: String?
    private var loginItem: NSMenuItem?
    private var installer: Process?
    private var installerBuffer = Data()
    private var installationStatus: String?
    private var runtimeMessage: String?
    private var networkStarted = false
    private var advertisement: NetService?
    private lazy var networkCoordinator: NetworkCoordinator = {
        let coordinator = NetworkCoordinator()
        coordinator.status = { [weak self] network in self?.send("network-status",values:["network":network as Any? ?? NSNull()]) }
        coordinator.completion = { [weak self] identifier,network,reason in
            self?.send("network-update",values:["requestId":identifier,"network":network as Any? ?? NSNull(),"error":network == nil,"reason":reason as Any? ?? NSNull()])
        }
        return coordinator
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength:28)
        if let button = item.button { menuBarIcon = MenuBarStatusIcon(button:button) }
        updateMenuBar(state:"connecting",description:"正在启动")
        let menu = NSMenu()
        menuStatus.isEnabled = false
        menu.addItem(menuStatus)
        menu.addItem(.separator())
        menu.addItem(withTitle: "打开详情", action: #selector(showDetails), keyEquivalent: "")
        menu.addItem(withTitle: "更新手机 App", action: #selector(updatePhone), keyEquivalent: "")
        menu.addItem(withTitle: "初始化或更新网络授权…", action: #selector(authorizeNetwork), keyEquivalent: "")
        menu.addItem(withTitle: "导入运行时认证材料…", action: #selector(importRuntimeAuthentication), keyEquivalent: "")
        menu.addItem(withTitle: "检查当前网络", action: #selector(checkNetwork), keyEquivalent: "")
        menu.addItem(withTitle: "停止报点", action: #selector(stop), keyEquivalent: "")
        menu.addItem(withTitle: "配对手机控制端", action: #selector(createPairing), keyEquivalent: "")
        let login = menu.addItem(withTitle: "登录时自动运行", action: #selector(toggleLogin), keyEquivalent: "")
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        loginItem = login
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(quit), keyEquivalent: "q")
        for entry in menu.items { entry.target = self }
        statusMenuController = MenuBarStatusMenu(menu:menu,statusItem:item)
        makeWindow()
        startHost()
        if ProcessInfo.processInfo.arguments.contains("--pair") { DispatchQueue.main.asyncAfter(deadline:.now()+2) { self.createPairing() } }
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(sleep), name: NSWorkspace.willSleepNotification, object: nil)
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.send("status") }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showDetails(); return true
    }

    private func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0,y: 0,width: 520,height: 610), styleMask: [.titled,.closable,.miniaturizable], backing: .buffered, defer: false)
        window.title = "Loc2"
        window.isReleasedWhenClosed = false
        window.center()
        let content = NSStackView()
        content.orientation = .vertical
        content.alignment = .leading
        content.spacing = 14
        content.edgeInsets = NSEdgeInsets(top: 24,left: 24,bottom: 24,right: 24)
        content.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor),
            content.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor),
            content.topAnchor.constraint(equalTo: window.contentView!.topAnchor)
        ])
        let title = NSTextField(labelWithString: "定位会话诊断")
        title.font = .systemFont(ofSize: 22,weight: .semibold)
        content.addArrangedSubview(title)
        statusText.preferredMaxLayoutWidth = 450
        content.addArrangedSubview(statusText)
        content.addArrangedSubview(NSTextField(labelWithString: "选点草稿 · WGS84（纬度、经度）"))
        let fields = NSStackView(views: [latitude,longitude]);fields.spacing = 12
        latitude.placeholderString = "纬度 -90…90";longitude.placeholderString = "经度 -180…180"
        latitude.widthAnchor.constraint(equalToConstant: 210).isActive = true
        longitude.widthAnchor.constraint(equalToConstant: 210).isActive = true
        content.addArrangedSubview(fields)
        content.addArrangedSubview(NSStackView(views: [button("应用位置", #selector(apply)),button("停止报点",#selector(stop))]))
        targetText.preferredMaxLayoutWidth = 450
        content.addArrangedSubview(targetText)
        content.addArrangedSubview(button("检查当前网络",#selector(checkNetwork)))
        content.addArrangedSubview(NSStackView(views: [button("已观察到目标位置",#selector(confirmAdoption)),button("已恢复真实位置",#selector(confirmRecovery))]))
        let hint = NSTextField(wrappingLabelWithString: "停止报点不等于恢复真实位置。请在手机地图中单独检查；必要时手动关闭再开启定位服务。")
        hint.textColor = .secondaryLabelColor
        hint.preferredMaxLayoutWidth = 450
        content.addArrangedSubview(hint)
        content.addArrangedSubview(button("配对手机控制端",#selector(createPairing)))
        makePairingWindow()
    }

    private func makePairingWindow() {
        pairingWindow = NSWindow(contentRect: NSRect(x:0,y:0,width:540,height:620),styleMask:[.titled,.closable],backing:.buffered,defer:false)
        pairingWindow.title = "配对手机控制端"
        pairingWindow.isReleasedWhenClosed = false
        pairingWindow.center()
        let content = NSStackView()
        content.orientation = .vertical;content.alignment = .leading;content.spacing = 14
        content.edgeInsets = NSEdgeInsets(top:24,left:24,bottom:24,right:24)
        content.translatesAutoresizingMaskIntoConstraints = false
        pairingWindow.contentView!.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo:pairingWindow.contentView!.leadingAnchor),
            content.trailingAnchor.constraint(equalTo:pairingWindow.contentView!.trailingAnchor),
            content.topAnchor.constraint(equalTo:pairingWindow.contentView!.topAnchor)
        ])
        phoneText.preferredMaxLayoutWidth = 460
        content.addArrangedSubview(phoneText)
        qrImage.imageScaling = .scaleProportionallyUpOrDown
        qrImage.widthAnchor.constraint(equalToConstant: 260).isActive = true
        qrImage.heightAnchor.constraint(equalToConstant: 260).isActive = true
        let pairBox = NSStackView(views: [qrImage,button("生成配对二维码",#selector(createPairing))]);pairBox.spacing = 16
        content.addArrangedSubview(pairBox)
        pendingRequests.widthAnchor.constraint(equalToConstant: 460).isActive = true
        content.addArrangedSubview(pendingRequests)
        content.addArrangedSubview(NSStackView(views: [button("允许所选控制端",#selector(approvePairing)),button("拒绝",#selector(denyPairing))]))
        content.addArrangedSubview(NSTextField(labelWithString:"已授权控制端"))
        authorizedControllers.widthAnchor.constraint(equalToConstant:460).isActive = true
        content.addArrangedSubview(authorizedControllers)
        content.addArrangedSubview(NSStackView(views:[button("绑定蓝牙目标…",#selector(bindBluetoothTarget)),button("撤销所选控制端授权",#selector(revokeAuthorization))]))
    }

    private func button(_ title: String, _ selector: Selector) -> NSButton {
        NSButton(title: title,target: self,action: selector)
    }

    private func startHost() {
        let task = Process()
        let resources = Bundle.main.resourceURL ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let bundledPython = resources.appendingPathComponent("Python/bin/python3")
        task.executableURL = URL(fileURLWithPath:ProcessInfo.processInfo.environment["LOC2_PYTHON"] ?? (FileManager.default.isExecutableFile(atPath:bundledPython.path) ? bundledPython.path : "/usr/bin/python3"))
        task.arguments = ["-m","loc2.local_host"]
        task.currentDirectoryURL = resources
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = resources.path
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        task.environment = environment
        let incoming = Pipe(), outgoing = Pipe()
        task.standardInput = incoming;task.standardOutput = outgoing
        // Host sanitizes responses; discard unexpected diagnostics rather than exposing private paths.
        task.standardError = FileHandle.nullDevice
        input = incoming.fileHandleForWriting
        outgoing.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.receive(data) }
        }
        task.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, !self.terminating else { return }
                self.statusText.stringValue = "本机会话服务已退出。请检查 Python 3 与运行时配置后重新打开应用。"
                self.updateMenuBar(state:"error",description:"本机会话服务已退出")
                self.input = nil
            }
        }
        do { try task.run();process = task;send("status") }
        catch {
            statusText.stringValue = "无法启动 Python 3 会话服务，请检查本机环境。";input = nil
            updateMenuBar(state:"error",description:"本机会话服务启动失败")
        }
    }

    private func send(_ action: String, values: [String: Any] = [:]) {
        guard let input = input else { return }
        var request = values
        request["action"] = action;request["id"] = UUID().uuidString
        guard var data = try? JSONSerialization.data(withJSONObject: request) else { return }
        data.append(10)
        do { try input.write(contentsOf: data) }
        catch {
            self.input = nil;statusText.stringValue = "本机会话服务连接已断开"
            updateMenuBar(state:"error",description:"本机会话服务连接已断开")
        }
    }

    private func receive(_ data: Data) {
        outputBuffer.append(data)
        while let newline = outputBuffer.firstIndex(of: 10) {
            let line = outputBuffer[..<newline]
            outputBuffer.removeSubrange(...newline)
            guard let response = (try? JSONSerialization.jsonObject(with: line)) as? [String: Any] else { continue }
            if response["networkAutoEnabled"] as? Bool == true && !networkStarted {
                networkStarted = true;networkCoordinator.start()
            }
            if response["event"] as? String == "network-request",let identifier = response["requestId"] as? String {
                networkCoordinator.request(identifier,interactive:response["interactive"] as? Bool ?? false);continue
            }
            if let runtime = response["runtime"] as? [String:Any] { runtimeMessage = runtime["ready"] as? Bool == true ? nil : runtime["message"] as? String }
            if let snapshot = response["status"] as? [String: Any] { state = snapshot;render() }
            if let error = response["error"] as? String { statusText.stringValue = error }
            if let details = response["phone"] as? [String:Any] { phone = details;renderPhone() }
            if let error = response["error"] as? String, pairingWindow.isVisible { phoneText.stringValue = error }
            if let message = response["setupMessage"] as? String {
                let alert = NSAlert();alert.messageText = "蓝牙目标已绑定";alert.informativeText = message;alert.runModal()
            }
        }
    }

    private func updateMenuBar(state: String,description: String) {
        let update = { [weak self] in
            guard let self else { return }
            self.menuBarIcon?.update(state:state,description:description)
            let title = "Loc2 · \(description)"
            if self.menuStatus.title != title { self.menuStatus.title = title }
        }
        if let statusMenuController { statusMenuController.update(update) }
        else { update() }
    }

    private func render() {
        let names = ["ready":"就绪", "disconnected":"未连接", "connecting":"正在连接", "waiting-for-video":"正在准备定位会话", "waiting-for-subscription":"等待手机位置订阅", "reporting":"正在报点", "stopped":"已停止报点", "error":"异常"]
        let status = names[state["state"] as? String ?? ""] ?? "未知状态"
        updateMenuBar(state:state["state"] as? String ?? "disconnected",description:status)
        let count = (state["availableDevices"] as? [String])?.count ?? 0
        let adoption = state["adoption"] as? String == "user-confirmed" ? "位置采用：用户已确认" : "位置采用：未确认"
        let recovery = state["recovery"] as? String == "user-confirmed" ? "恢复：用户已确认" : state["recovery"] as? String == "pending" ? "恢复：待手机确认" : "恢复：暂无待确认"
        statusText.stringValue = "\(status) · 目标设备 \(count) 台\n\(adoption) · \(recovery)"
        if let lane = state["transport"] as? String {
            let name = lane == "usb" ? "USB" : lane == "bluetooth" ? "无线" : "待连接"
            statusText.stringValue += "\n报点通道：\(name)" + (state["transportPolicy"] as? String == "usb-preferred" ? " · USB 优先" : "")
        }
        if let hint = state["connectionHint"] as? String { statusText.stringValue += "\n" + hint }
        if let installationStatus { statusText.stringValue += "\n" + installationStatus }
        if let phase = state["diagnosticStage"] as? String {
            statusText.stringValue += "\n阶段：\(phase) · 解码帧：\(state["videoDecodedFrames"] ?? 0)"
        }
        if let message = runtimeMessage { statusText.stringValue += "\n" + message }
        if let error = state["error"] as? String { statusText.stringValue += "\n" + error }
        if let point = state["target"] as? [String: Any], let lat = point["latitude"] as? Double, let lon = point["longitude"] as? Double {
            targetText.stringValue = "已接受目标：\(lat), \(lon) · WGS84\n本地接受批次：\(state["helperAcceptedBatches"] ?? 0)（不代表手机采用）"
        } else { targetText.stringValue = "未应用目标位置；重连后需重新点击应用。" }
    }

    private func renderPhone() {
        phoneText.stringValue = phone["error"] as? String ?? "同一局域网扫码，无需 USB；扫码后需在此确认。控制端名称不是设备身份证明。"
        if phone["usbControlConnected"] as? Bool == true { phoneText.stringValue += "\nUSB 手机控制已连接" }
        if let device = phone["pairingDevice"] as? String { phoneText.stringValue += "\n目标手机：\(device)" }
        if advertisement == nil, let endpoint = phone["origin"] as? String,
           let url = URL(string: endpoint), url.scheme == "https", let port = url.port,
           let fingerprint = phone["serverFingerprint"] as? String {
            let service = NetService(domain: "local.", type: "_loc2._tcp.", name: "Loc2", port: Int32(port))
            service.setTXTRecord(NetService.data(fromTXTRecord: ["fingerprint":Data(fingerprint.utf8)]))
            service.publish(); advertisement = service
        }
        let url = phone["pairingURL"] as? String
        if url != lastPairingURL {
            lastPairingURL = url;qrImage.image = nil
            if let url = url, let filter = CIFilter(name: "CIQRCodeGenerator") {
                filter.setValue(Data(url.utf8), forKey: "inputMessage")
                filter.setValue("M",forKey: "inputCorrectionLevel")
                if let image = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 6,y: 6)), let cg = CIContext().createCGImage(image,from:image.extent) {
                    let padded = NSImage(size:NSSize(width:260,height:260))
                    padded.lockFocus()
                    NSColor.white.setFill();NSRect(x:0,y:0,width:260,height:260).fill()
                    NSGraphicsContext.current?.imageInterpolation = .none
                    NSImage(cgImage:cg,size:NSSize(width:236,height:236)).draw(in:NSRect(x:12,y:12,width:236,height:236))
                    padded.unlockFocus();qrImage.image = padded
                }
            }
        }
        let selectedRequestId = pendingRequests.selectedItem?.representedObject as? String
        pending = phone["pending"] as? [[String:Any]] ?? []
        pendingRequests.removeAllItems()
        pendingRequests.addItem(withTitle: pending.isEmpty ? "暂无待确认请求" : "请选择需要确认的控制端")
        for request in pending {
            pendingRequests.addItem(withTitle: "\(request["label"] ?? "控制端") → \(request["deviceId"] as? String ?? "仅连接授权，尚未配置报点目标")")
            pendingRequests.lastItem?.representedObject = request["requestId"] as? String
        }
        if let selectedRequestId = selectedRequestId,
           let selectedItem = pendingRequests.itemArray.first(where: { $0.representedObject as? String == selectedRequestId }) {
            pendingRequests.select(selectedItem)
        }
        pendingRequests.isEnabled = !pending.isEmpty
        let selectedId = authorizedControllers.selectedItem?.representedObject as? String
        grants = phone["grants"] as? [[String:Any]] ?? []
        authorizedControllers.removeAllItems()
        authorizedControllers.addItem(withTitle: grants.isEmpty ? "暂无已授权控制端" : "请选择已授权控制端")
        for grant in grants {
            authorizedControllers.addItem(withTitle:"\(grant["label"] ?? "控制端") → \(grant["deviceId"] as? String ?? "待配置报点目标")")
            authorizedControllers.lastItem?.representedObject = grant["grantId"] as? String
        }
        if let selectedId = selectedId,
           let selectedItem = authorizedControllers.itemArray.first(where: { $0.representedObject as? String == selectedId }) {
            authorizedControllers.select(selectedItem)
        }
        authorizedControllers.isEnabled = !grants.isEmpty
    }
    @objc private func bindBluetoothTarget() {
        guard let id = authorizedControllers.selectedItem?.representedObject as? String,
              let grant = grants.first(where:{ $0["grantId"] as? String == id }) else {
            phoneText.stringValue = "请先扫码批准手机，再选择已授权控制端";return
        }
        guard state["sessionId"] == nil || state["sessionId"] is NSNull,state["recovery"] as? String != "pending" else {
            phoneText.stringValue = "请先停止当前会话并确认恢复真实位置";return
        }
        let setup = BluetoothTargetSetup()
        guard let (address,interface) = setup.run(controllerName:grant["label"] as? String ?? "手机") else { return }
        send("bind-wireless-target",values:["grantId":id,"address":address,"wifiInterface":interface])
    }

    @objc private func revokeAuthorization() {
        guard let id = authorizedControllers.selectedItem?.representedObject as? String,
              grants.contains(where: { $0["grantId"] as? String == id }) else { return }
        send("pairing-revoke",values:["grantId":id])
    }
    @objc private func createPairing() { pairingWindow.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);send("pairing-create") }
    @objc private func approvePairing() {
        guard let id = pendingRequests.selectedItem?.representedObject as? String,
              pending.contains(where: { $0["requestId"] as? String == id }) else { return }
        send("pairing-approve",values:["requestId":id])
    }
    @objc private func denyPairing() {
        guard let id = pendingRequests.selectedItem?.representedObject as? String,
              pending.contains(where: { $0["requestId"] as? String == id }) else { return }
        send("pairing-deny",values:["requestId":id])
    }
    @objc private func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            else { try SMAppService.mainApp.register() }
            loginItem?.state = SMAppService.mainApp.status == .enabled ? .on : .off
        } catch {
            let alert = NSAlert(); alert.messageText = "无法更新登录启动设置"
            alert.informativeText = "请将应用保留在固定位置，并在系统设置的登录项中确认授权。"
            alert.runModal()
        }
    }

    @objc private func showDetails() { window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps: true) }
    @objc private func apply() {
        guard let lat = Double(latitude.stringValue), let lon = Double(longitude.stringValue), lat.isFinite, lon.isFinite else {
            statusText.stringValue = "请输入有效 WGS84 经纬度";return
        }
        guard let devices = state["availableDevices"] as? [String], devices.count == 1 else {
            statusText.stringValue = "请连接已绑定的目标 iPhone";return
        }
        var values: [String:Any] = ["deviceId":devices[0],"point":["latitude":lat,"longitude":lon]]
        if let session = state["sessionId"] as? String { values["sessionId"] = session }
        send("apply",values:values)
    }
    @objc private func updatePhone() {
        guard state["sessionId"] == nil || state["sessionId"] is NSNull else { statusText.stringValue = "请先恢复位置，再更新手机 App";showDetails();return }
        guard installer == nil else { showDetails();return }
        let configURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/loc2/config.json")
        guard let data = try? Data(contentsOf:configURL),let config = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
              let mobile = config["mobile"] as? [String:Any],let root = mobile["projectRoot"] as? String else {
            statusText.stringValue = "尚未配置本机手机安装环境";showDetails();return
        }
        let task = Process(), pipe = Pipe()
        task.executableURL = URL(fileURLWithPath:"/usr/bin/python3")
        task.arguments = [URL(fileURLWithPath:root).appendingPathComponent("scripts/install-ios-app.py").path,"--config",configURL.path]
        task.standardOutput = pipe;task.standardError = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] file in
            let data = file.availableData
            if data.isEmpty { file.readabilityHandler = nil;return }
            DispatchQueue.main.async {
                guard let self else { return };self.installerBuffer.append(data)
                while let newline = self.installerBuffer.firstIndex(of:10) {
                    let line = self.installerBuffer[..<newline];self.installerBuffer.removeSubrange(...newline)
                    if let value = (try? JSONSerialization.jsonObject(with:line)) as? [String:Any],let stage = value["stage"] as? String {
                        self.installationStatus = stage;self.render()
                    }
                }
            }
        }
        task.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.installer = nil } }
        do { try task.run();installer = task;showDetails() }
        catch { statusText.stringValue = "无法启动手机更新工具";showDetails() }
    }

    @objc private func importRuntimeAuthentication() {
        let panel = NSOpenPanel()
        panel.title = "导入本机运行时认证材料"
        panel.message = "选择包含 identity.pk8 与 certificate.p7b 的 authentication 目录。材料只保存在本机，不上传；已有身份不会被覆盖。"
        panel.canChooseDirectories = true;panel.canChooseFiles = false;panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK,let url = panel.url else { return }
        showDetails();send("import-runtime-authentication",values:["directory":url.path])
    }

    @objc private func authorizeNetwork() { showDetails();send("network-authorize") }
    @objc private func checkNetwork() { showDetails();send("network-prepare") }
    @objc private func stop() { send("stop") }
    @objc private func sleep() { send("sleep") }
    @objc private func confirmAdoption() {
        guard let session = state["sessionId"] as? String, let revision = state["controlRevision"] as? Int else { return }
        send("confirm-adoption",values:["sessionId":session,"controlRevision":revision])
    }
    @objc private func confirmRecovery() {
        guard let revision = state["controlRevision"] as? Int else { return }
        send("confirm-recovery",values:["controlRevision":revision])
    }
    @objc private func quit() { NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        terminating = true;timer?.invalidate();installer?.terminate();send("quit")
        try? input?.close();input = nil
        guard let process = process, process.isRunning else { return .terminateNow }
        DispatchQueue.global().async {
            let deadline = Date().addingTimeInterval(8)
            while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if process.isRunning { process.terminate() }
            DispatchQueue.main.async { sender.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}

signal(SIGPIPE, SIG_IGN)
let app = NSApplication.shared
let delegate = LocationApp()
app.delegate = delegate
app.run()
