import AppKit
import Foundation
import CoreImage
import Darwin

final class LocationApp: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
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
    private var phone: [String:Any] = [:]
    private var pending: [[String:Any]] = []
    private var lastPairingURL: String?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Location Lab"
        let menu = NSMenu()
        menu.addItem(withTitle: "打开详情", action: #selector(showDetails), keyEquivalent: "")
        menu.addItem(withTitle: "停止报点", action: #selector(stop), keyEquivalent: "")
        menu.addItem(withTitle: "配对手机控制端", action: #selector(createPairing), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(quit), keyEquivalent: "q")
        for entry in menu.items { entry.target = self }
        item.menu = menu
        makeWindow()
        startHost()
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(sleep), name: NSWorkspace.willSleepNotification, object: nil)
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.send("status") }
        showDetails()
    }

    private func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0,y: 0,width: 500,height: 500), styleMask: [.titled,.closable,.miniaturizable], backing: .buffered, defer: false)
        window.title = "Location Lab"
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
        let title = NSTextField(labelWithString: "USB 定位会话")
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
        content.addArrangedSubview(NSStackView(views: [button("已观察到目标位置",#selector(confirmAdoption)),button("已恢复真实位置",#selector(confirmRecovery))]))
        let hint = NSTextField(wrappingLabelWithString: "停止报点不等于恢复真实位置。请在手机地图中单独检查；必要时手动关闭再开启定位服务。")
        hint.textColor = .secondaryLabelColor
        hint.preferredMaxLayoutWidth = 450
        content.addArrangedSubview(hint)
        content.addArrangedSubview(button("配对手机控制端",#selector(createPairing)))
        makePairingWindow()
    }

    private func makePairingWindow() {
        pairingWindow = NSWindow(contentRect: NSRect(x:0,y:0,width:540,height:460),styleMask:[.titled,.closable],backing:.buffered,defer:false)
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
        qrImage.widthAnchor.constraint(equalToConstant: 174).isActive = true
        qrImage.heightAnchor.constraint(equalToConstant: 174).isActive = true
        let pairBox = NSStackView(views: [qrImage,button("生成配对二维码",#selector(createPairing))]);pairBox.spacing = 16
        content.addArrangedSubview(pairBox)
        pendingRequests.widthAnchor.constraint(equalToConstant: 460).isActive = true
        content.addArrangedSubview(pendingRequests)
        content.addArrangedSubview(NSStackView(views: [button("允许所选控制端",#selector(approvePairing)),button("拒绝",#selector(denyPairing))]))
    }

    private func button(_ title: String, _ selector: Selector) -> NSButton {
        NSButton(title: title,target: self,action: selector)
    }

    private func startHost() {
        let task = Process()
        let resources = Bundle.main.resourceURL ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        task.executableURL = URL(fileURLWithPath: ProcessInfo.processInfo.environment["LOCATION_LAB_PYTHON"] ?? "/usr/bin/python3")
        task.arguments = ["-m","location_lab.local_host"]
        task.currentDirectoryURL = resources
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = resources.path
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
                self.item.button?.title = "Location Lab · 异常"
                self.input = nil
            }
        }
        do { try task.run();process = task;send("status") }
        catch { statusText.stringValue = "无法启动 Python 3 会话服务，请检查本机环境。";input = nil }
    }

    private func send(_ action: String, values: [String: Any] = [:]) {
        guard let input = input else { return }
        var request = values
        request["action"] = action;request["id"] = UUID().uuidString
        guard var data = try? JSONSerialization.data(withJSONObject: request) else { return }
        data.append(10)
        do { try input.write(contentsOf: data) }
        catch { self.input = nil;statusText.stringValue = "本机会话服务连接已断开" }
    }

    private func receive(_ data: Data) {
        outputBuffer.append(data)
        while let newline = outputBuffer.firstIndex(of: 10) {
            let line = outputBuffer[..<newline]
            outputBuffer.removeSubrange(...newline)
            guard let response = (try? JSONSerialization.jsonObject(with: line)) as? [String: Any] else { continue }
            if let snapshot = response["status"] as? [String: Any] { state = snapshot;render() }
            if let error = response["error"] as? String { statusText.stringValue = error }
            if let details = response["phone"] as? [String:Any] { phone = details;renderPhone() }
            if let error = response["error"] as? String, pairingWindow.isVisible { phoneText.stringValue = error }
        }
    }

    private func render() {
        let names = ["ready":"就绪", "disconnected":"未连接", "connecting":"正在连接", "waiting-for-subscription":"等待手机位置订阅", "reporting":"正在报点", "stopped":"已停止报点", "error":"异常"]
        let status = names[state["state"] as? String ?? ""] ?? "未知状态"
        item.button?.title = "Location Lab · \(status)"
        let count = (state["availableDevices"] as? [String])?.count ?? 0
        let adoption = state["adoption"] as? String == "user-confirmed" ? "位置采用：用户已确认" : "位置采用：未确认"
        let recovery = state["recovery"] as? String == "user-confirmed" ? "恢复：用户已确认" : state["recovery"] as? String == "pending" ? "恢复：待手机确认" : "恢复：暂无待确认"
        statusText.stringValue = "\(status) · USB 设备 \(count) 台\n\(adoption) · \(recovery)"
        if let error = state["error"] as? String { statusText.stringValue += "\n" + error }
        if let point = state["target"] as? [String: Any], let lat = point["latitude"] as? Double, let lon = point["longitude"] as? Double {
            targetText.stringValue = "已接受目标：\(lat), \(lon) · WGS84\n本地接受批次：\(state["helperAcceptedBatches"] ?? 0)（不代表手机采用）"
        } else { targetText.stringValue = "未应用目标位置；重连后需重新点击应用。" }
    }

    private func renderPhone() {
        phoneText.stringValue = phone["error"] as? String ?? "扫码后需在此确认。控制端名称由浏览器声明，不是设备身份证明。"
        if let device = phone["pairingDevice"] as? String { phoneText.stringValue += "\n目标 USB 手机：\(device)" }
        let url = phone["pairingURL"] as? String
        if url != lastPairingURL {
            lastPairingURL = url;qrImage.image = nil
            if let url = url, let filter = CIFilter(name: "CIQRCodeGenerator") {
                filter.setValue(Data(url.utf8), forKey: "inputMessage")
                filter.setValue("M",forKey: "inputCorrectionLevel")
                if let image = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 6,y: 6)), let cg = CIContext().createCGImage(image,from:image.extent) {
                    let padded = NSImage(size:NSSize(width:174,height:174))
                    padded.lockFocus()
                    NSColor.white.setFill();NSRect(x:0,y:0,width:174,height:174).fill()
                    NSGraphicsContext.current?.imageInterpolation = .none
                    NSImage(cgImage:cg,size:NSSize(width:150,height:150)).draw(in:NSRect(x:12,y:12,width:150,height:150))
                    padded.unlockFocus();qrImage.image = padded
                }
            }
        }
        let selection = pendingRequests.indexOfSelectedItem
        pending = phone["pending"] as? [[String:Any]] ?? []
        pendingRequests.removeAllItems()
        for request in pending {
            pendingRequests.addItem(withTitle: "\(request["label"] ?? "控制端") → \(request["deviceId"] ?? "未知手机")")
        }
        if pending.isEmpty { pendingRequests.addItem(withTitle: "暂无待确认请求") }
        else if selection >= 0 && selection < pending.count { pendingRequests.selectItem(at:selection) }
        pendingRequests.isEnabled = !pending.isEmpty
    }
    @objc private func createPairing() { pairingWindow.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);send("pairing-create") }
    @objc private func approvePairing() {
        let index = pendingRequests.indexOfSelectedItem
        guard pending.indices.contains(index), let id = pending[index]["requestId"] as? String else { return }
        send("pairing-approve",values:["requestId":id])
    }
    @objc private func denyPairing() {
        let index = pendingRequests.indexOfSelectedItem
        guard pending.indices.contains(index), let id = pending[index]["requestId"] as? String else { return }
        send("pairing-deny",values:["requestId":id])
    }
    @objc private func showDetails() { window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps: true) }
    @objc private func apply() {
        guard let lat = Double(latitude.stringValue), let lon = Double(longitude.stringValue), lat.isFinite, lon.isFinite else {
            statusText.stringValue = "请输入有效 WGS84 经纬度";return
        }
        guard let devices = state["availableDevices"] as? [String], devices.count == 1 else {
            statusText.stringValue = "请连接且仅连接指定的一台 USB iPhone";return
        }
        var values: [String:Any] = ["deviceId":devices[0],"point":["latitude":lat,"longitude":lon]]
        if let session = state["sessionId"] as? String { values["sessionId"] = session }
        send("apply",values:values)
    }
    @objc private func stop() { send("stop") }
    @objc private func sleep() { send("sleep") }
    @objc private func confirmAdoption() {
        guard let session = state["sessionId"] as? String else { return }
        send("confirm-adoption",values:["sessionId":session])
    }
    @objc private func confirmRecovery() { send("confirm-recovery") }
    @objc private func quit() { NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        terminating = true;timer?.invalidate();send("quit")
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
