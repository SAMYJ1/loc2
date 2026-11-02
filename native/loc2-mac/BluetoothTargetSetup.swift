import AppKit
import CoreWLAN
import IOBluetooth

/// System discovery/pairing supplies the address; users never need to type it.
final class BluetoothTargetSetup: NSObject {
    private let devices = NSPopUpButton()
    private let status = NSTextField(wrappingLabelWithString:"尚未选择手机")
    private let verified = NSButton(checkboxWithTitle:"确认所选设备是刚才扫码授权的这台 iPhone",target:nil,action:nil)
    private var selected: IOBluetoothDevice?
    private var activationObserver: NSObjectProtocol?

    func run(controllerName: String) -> (String,String)? {
        let alert = NSAlert()
        alert.messageText = "连接并绑定蓝牙目标"
        alert.informativeText = "为「\(controllerName)」绑定报点手机，无需 USB。\n在 iPhone 打开「设置 → 蓝牙」并保持页面打开，点击下方搜索，在 Mac 系统蓝牙页面选择手机并确认配对，完成后返回这里。已配对的手机可直接从列表选择。"
        alert.addButton(withTitle:"确认绑定")
        alert.addButton(withTitle:"取消")
        let stack = NSStackView()
        stack.orientation = .vertical;stack.alignment = .leading;stack.spacing = 10
        stack.frame = NSRect(x:0,y:0,width:460,height:160)
        stack.addArrangedSubview(NSButton(title:"搜索并配对附近手机…",target:self,action:#selector(searchAndPair)))
        devices.target = self;devices.action = #selector(selectDevice)
        devices.widthAnchor.constraint(equalToConstant:460).isActive = true
        stack.addArrangedSubview(devices)
        stack.addArrangedSubview(NSButton(title:"刷新已配对手机",target:self,action:#selector(refresh)))
        status.preferredMaxLayoutWidth = 460
        status.widthAnchor.constraint(equalToConstant:460).isActive = true
        stack.addArrangedSubview(status)
        stack.addArrangedSubview(verified)
        alert.accessoryView = stack
        refresh()
        activationObserver = NotificationCenter.default.addObserver(forName:NSApplication.didBecomeActiveNotification,object:NSApp,queue:.main) { [weak self] _ in self?.refresh() }
        defer { if let activationObserver { NotificationCenter.default.removeObserver(activationObserver) };activationObserver = nil }
        while alert.runModal() == .alertFirstButtonReturn {
            guard verified.state == .on,let device = selected,device.isPaired(),
                  let raw = device.addressString else {
                alert.messageText = "请选择已配对的手机，并确认这是扫码的同一台设备";continue
            }
            let address = raw.replacingOccurrences(of:"-",with:":").lowercased()
            guard address.range(of:"^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$",options:.regularExpression) != nil else {
                alert.messageText = "无法读取设备地址，请重新搜索配对";continue
            }
            guard let interface = CWWiFiClient.shared().interface()?.interfaceName else {
                alert.messageText = "请先连接 Mac 的 Wi-Fi 网络";continue
            }
            return (address,interface)
        }
        return nil
    }

    @objc private func searchAndPair() {
        selected = nil;verified.state = .off
        // The legacy embedded pairing panel returns immediately on current macOS.
        // Use the system Bluetooth page for discovery and OS-owned pairing prompts.
        let opened = NSWorkspace.shared.open(URL(string:"x-apple.systempreferences:com.apple.BluetoothSettings")!)
        status.stringValue = opened ? "在系统蓝牙页面选择 iPhone 并确认配对，然后返回这里选择手机；设备列表会自动刷新。" : "无法打开系统设置，请手动打开 Mac 的蓝牙设置完成配对后刷新。"
    }

    @objc private func refresh() {
        selected = nil;verified.state = .off
        devices.removeAllItems()
        devices.addItem(withTitle:"选择已配对手机")
        for device in (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []) where device.deviceClassMajor == 2 {
            guard let address = device.addressString else { continue }
            devices.addItem(withTitle:"\(device.name ?? "手机") · \(address.suffix(5)) · \(device.isConnected() ? "已连接" : "已配对")")
            devices.lastItem?.representedObject = device
        }
        status.stringValue = devices.numberOfItems > 1 ? "请选择手机，或搜索配对新手机" : "暂无已配对手机，请点击搜索"
    }

    @objc private func selectDevice() {
        selected = devices.selectedItem?.representedObject as? IOBluetoothDevice
        verified.state = .off
        showSelection()
    }

    private func showSelection() {
        guard let device = selected else { status.stringValue = "尚未选择手机";return }
        status.stringValue = "\(device.name ?? "手机")：\(device.isConnected() ? "蓝牙已连接" : "系统配对已完成")。确认后绑定到所选控制端；定位通道在应用位置时启动。"
    }
}
