import AppKit

/// GitHub CLI owns login credentials; only a verified private staging directory
/// crosses the app's existing local import channel.
final class GitHubImportController: NSObject, NSWindowDelegate {
    private let window = NSWindow(contentRect:NSRect(x:0,y:0,width:540,height:360),styleMask:[.titled,.closable],backing:.buffered,defer:false)
    private let status = NSTextField(wrappingLabelWithString:"")
    private let code = NSTextField(labelWithString:"")
    private let beginButton = NSButton(title:"登录并导入",target:nil,action:nil)
    private let loginButton = NSButton(title:"更换 GitHub 账号…",target:nil,action:nil)
    private let cancelButton = NSButton(title:"关闭",target:nil,action:nil)
    private var process: Process?
    private var output = Data()
    private var staging: URL?
    private var pendingImport: String?
    private var importTimeout: Timer?
    private var canceled = false
    private var busy = false
    private var openedBrowser = false
    var importDirectory: ((String,String) -> Void)?

    override init() {
        super.init()
        window.title = "从 GitHub 导入认证材料";window.isReleasedWhenClosed = false;window.delegate = self
        let stack = NSStackView();stack.orientation = .vertical;stack.alignment = .leading;stack.spacing = 16
        stack.edgeInsets = NSEdgeInsets(top:24,left:24,bottom:24,right:24);stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:window.contentView!.leadingAnchor),stack.trailingAnchor.constraint(equalTo:window.contentView!.trailingAnchor),stack.topAnchor.constraint(equalTo:window.contentView!.topAnchor)])
        let hint = NSTextField(wrappingLabelWithString:"来源：SAMYJ1/loc2-private-auth\n使用有仓库访问权限的账号登录；浏览器授权应用名称为 GitHub CLI。下载校验后仅导入本机，已有不同身份不会被覆盖。")
        hint.preferredMaxLayoutWidth = 490;stack.addArrangedSubview(hint)
        status.preferredMaxLayoutWidth = 490;stack.addArrangedSubview(status)
        code.font = .monospacedSystemFont(ofSize:22,weight:.semibold);code.isSelectable = true;stack.addArrangedSubview(code)
        beginButton.target = self;beginButton.action = #selector(begin)
        loginButton.target = self;loginButton.action = #selector(loginAgain)
        cancelButton.target = self;cancelButton.action = #selector(cancelOrClose)
        stack.addArrangedSubview(NSStackView(views:[beginButton,loginButton,cancelButton]))
    }

    func show() {
        window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        if !busy { start(forceLogin:false) }
    }
    @objc private func begin() { start(forceLogin:false) }
    @objc private func loginAgain() { start(forceLogin:true) }

    private var gh: URL? {
        let resources = Bundle.main.resourceURL!
        return [resources.appendingPathComponent("GitHubCLI/bin/gh"),URL(fileURLWithPath:"/opt/homebrew/bin/gh"),URL(fileURLWithPath:"/usr/local/bin/gh")].first { FileManager.default.isExecutableFile(atPath:$0.path) }
    }
    private func environment() -> [String:String] {
        var env = ProcessInfo.processInfo.environment
        for key in ["GH_TOKEN","GITHUB_TOKEN","GH_ENTERPRISE_TOKEN","GITHUB_ENTERPRISE_TOKEN","GH_DEBUG","GH_CONFIG_DIR","GH_HOST","GH_FORCE_TTY","GH_PROMPT_DISABLED"] { env.removeValue(forKey:key) }
        env["GH_NO_UPDATE_NOTIFIER"] = "1";env["NO_COLOR"] = "1";env["GH_BROWSER"] = "/usr/bin/true"
        env["PYTHONNOUSERSITE"] = "1";env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env
    }
    private func start(forceLogin:Bool) {
        guard !busy else { return }
        guard let gh else { finish("当前 App 未包含 GitHub 登录组件，请安装新版完整 Release");return }
        busy = true;canceled = false;openedBrowser = false;code.stringValue = ""
        beginButton.isEnabled = false;loginButton.isEnabled = false;cancelButton.title = "取消"
        status.stringValue = "正在检查 GitHub 登录状态…"
        if forceLogin { authenticate(gh);return }
        run(gh,["auth","status","--hostname","github.com"]) { [weak self] success,_ in
            guard let self else { return }
            if success { self.download(gh) } else { self.authenticate(gh) }
        }
    }
    private func authenticate(_ gh: URL) {
        status.stringValue = "正在请求 GitHub 登录验证码…"
        run(gh,["auth","login","--hostname","github.com","--web","--git-protocol","https","--skip-ssh-key"],login:true) { [weak self] success,_ in
            guard let self else { return }
            self.code.stringValue = ""
            if success { self.download(gh) }
            else { self.finish("GitHub 登录未完成，请重试或检查浏览器中的授权结果") }
        }
    }
    private func download(_ gh: URL) {
        status.stringValue = "已登录，正在下载并校验认证材料…"
        do {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent("loc2-github-"+UUID().uuidString)
            try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
            staging = root
            let resources = Bundle.main.resourceURL!
            let bundled = resources.appendingPathComponent("Python/bin/python3")
            let python = URL(fileURLWithPath:ProcessInfo.processInfo.environment["LOC2_PYTHON"] ?? (FileManager.default.isExecutableFile(atPath:bundled.path) ? bundled.path : "/usr/bin/python3"))
            run(python,["-m","loc2.github_materials","--gh",gh.path,"--output",root.path]) { [weak self] success,data in
                guard let self else { return }
                let value = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
                guard success,value?["ok"] as? Bool == true else {
                    self.finish(value?["message"] as? String ?? "下载未完成，请检查网络和仓库权限后重试");return
                }
                guard let importDirectory = self.importDirectory else { self.finish("本机会话服务未就绪，请重新打开 App");return }
                self.status.stringValue = "校验通过，正在导入本机…"
                self.cancelButton.isEnabled = false;self.window.standardWindowButton(.closeButton)?.isEnabled = false
                let identifier = UUID().uuidString;self.pendingImport = identifier
                importDirectory(root.appendingPathComponent("authentication").path,identifier)
                self.importTimeout = Timer.scheduledTimer(withTimeInterval:15,repeats:false) { [weak self] _ in self?.finish("导入结果未返回，请查看 Mac 详情中的运行时状态") }
            }
        } catch { finish("无法创建私有下载目录，请检查本机磁盘权限") }
    }

    private func run(_ executable:URL,_ arguments:[String],login:Bool = false,completion:@escaping (Bool,Data)->Void) {
        let task = Process(),pipe = Pipe(),input = Pipe()
        task.executableURL = executable;task.arguments = arguments
        task.currentDirectoryURL = Bundle.main.resourceURL
        var env = environment();env["PYTHONPATH"] = Bundle.main.resourceURL!.path;task.environment = env
        task.standardInput = input;task.standardOutput = pipe;task.standardError = login ? pipe : FileHandle.nullDevice
        process = task;output.removeAll()
        if login { pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil;return }
            DispatchQueue.main.async {
                guard let self,self.process === task else { return }
                if self.output.count < 16384 { self.output.append(data.prefix(16384-self.output.count)) }
                if login { self.showDeviceCode() }
            }
        }
        }
        task.terminationHandler = { [weak self] _ in
            // Drain remaining sanitized worker output after the process exits.
            pipe.fileHandleForReading.readabilityHandler = nil
            let remainder = pipe.fileHandleForReading.readDataToEndOfFile()
            task.terminationHandler = nil
            DispatchQueue.main.async {
                guard let self,self.process === task else { return }
                self.output.append(remainder.prefix(max(0,16384-self.output.count)))
                let result = self.output;self.output.removeAll();self.process = nil
                if self.canceled { self.finish("已取消，本次未继续导入");return }
                completion(task.terminationStatus == 0,result)
            }
        }
        do { try task.run();try? input.fileHandleForWriting.write(contentsOf:Data("\n".utf8));try? input.fileHandleForWriting.close() }
        catch { task.terminationHandler = nil;pipe.fileHandleForReading.readabilityHandler = nil;process = nil;finish("无法启动 GitHub 登录或下载组件，请重新安装完整 App") }
    }
    private func showDeviceCode() {
        guard !openedBrowser,let text = String(data:output,encoding:.utf8),
              let range = text.range(of:"\\b[A-Z0-9]{4}-[A-Z0-9]{4}\\b",options:.regularExpression) else { return }
        openedBrowser = true;code.stringValue = String(text[range])
        status.stringValue = "请在浏览器登录 GitHub，并输入下方验证码完成授权；完成后会自动继续导入。"
        NSWorkspace.shared.open(URL(string:"https://github.com/login/device")!)
    }
    func receive(_ response:[String:Any]) {
        guard let pendingImport,response["id"] as? String == pendingImport else { return }
        finish(response["ok"] as? Bool == true ? "认证材料已导入，可以返回手机明确应用位置。" : (response["error"] as? String ?? "认证材料未导入，请检查本机状态"))
    }
    private func finish(_ message:String) {
        importTimeout?.invalidate();importTimeout = nil;pendingImport = nil
        if let staging { try? FileManager.default.removeItem(at:staging);self.staging = nil }
        output.removeAll();busy = false;code.stringValue = "";status.stringValue = message
        beginButton.isEnabled = true;loginButton.isEnabled = true;cancelButton.isEnabled = true;cancelButton.title = "关闭"
        window.standardWindowButton(.closeButton)?.isEnabled = true
    }
    @objc private func cancelOrClose() {
        if let process { canceled = true;status.stringValue = "正在取消…";process.terminate() }
        else if !busy { window.close() }
    }
    func windowWillClose(_ notification:Notification) { if process != nil { cancelOrClose() } }
    deinit { process?.terminate();if let staging { try? FileManager.default.removeItem(at:staging) } }
}
