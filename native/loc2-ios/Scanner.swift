import SwiftUI
import AVFoundation

struct QRScanner: UIViewControllerRepresentable {
    let scanned: (String) -> Void
    func makeUIViewController(context: Context) -> ScannerController { let controller = ScannerController(); controller.scanned = scanned; return controller }
    func updateUIViewController(_ uiViewController: ScannerController,context: Context) {}
    static func dismantleUIViewController(_ uiViewController: ScannerController, coordinator: ()) { uiViewController.stop() }
}
final class ScannerController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label:"loc2.camera")
    private var preview: AVCaptureVideoPreviewLayer?
    private var found = false
    var scanned: ((String) -> Void)?
    override func viewDidLoad() {
        super.viewDidLoad();view.backgroundColor = .black
        AVCaptureDevice.requestAccess(for:.video) { [weak self] allowed in
            guard let self else { return }
            if allowed { self.queue.async { self.configure() } }
            else { DispatchQueue.main.async { self.message("请在设置中允许相机，或粘贴连接邀请") } }
        }
    }
    private func configure() {
        guard let camera = AVCaptureDevice.default(for:.video),let input = try? AVCaptureDeviceInput(device:camera),session.canAddInput(input) else {
            DispatchQueue.main.async { self.message("相机不可用，可粘贴连接邀请") };return
        }
        session.addInput(input)
        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { return }
        session.addOutput(output);output.setMetadataObjectsDelegate(self,queue:.main);output.metadataObjectTypes = [.qr]
        DispatchQueue.main.async {
            let layer = AVCaptureVideoPreviewLayer(session:self.session);layer.videoGravity = .resizeAspectFill
            self.view.layer.insertSublayer(layer,at:0);self.preview = layer;layer.frame = self.view.bounds
        }
        session.startRunning()
    }
    override func viewDidLayoutSubviews() { super.viewDidLayoutSubviews();preview?.frame = view.bounds }
    private func message(_ text: String) {
        let label = UILabel();label.text = text;label.textColor = .white;label.numberOfLines = 0;label.textAlignment = .center;label.frame = view.bounds.insetBy(dx:20,dy:40);view.addSubview(label)
    }
    func metadataOutput(_ output: AVCaptureMetadataOutput,didOutput objects: [AVMetadataObject],from connection: AVCaptureConnection) {
        guard !found,let value = (objects.first as? AVMetadataMachineReadableCodeObject)?.stringValue,value.hasPrefix("loc2://") else { return }
        found = true;stop();scanned?(value)
    }
    func stop() { queue.async { [session] in if session.isRunning { session.stopRunning() } } }
}
