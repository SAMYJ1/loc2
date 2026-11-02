import AppKit

/// The app's central pin, without its background, adapts to the menu-bar appearance.
final class MenuBarStatusIcon {
    private enum Phase { case idle, ready, preparing, reporting, error }
    private let button: NSStatusBarButton
    private let badge = StatusBadgeView(frame:NSRect(x:18,y:2,width:8,height:8))
    private var phase: Phase?

    init(button: NSStatusBarButton) {
        self.button = button
        button.title = ""
        button.imagePosition = .imageOnly
        button.image = Self.makePinImage()
        button.addSubview(badge)
        badge.autoresizingMask = [.minXMargin,.maxYMargin]
        badge.setAccessibilityElement(false)
    }

    private static func makePinImage() -> NSImage {
        // Same geometry as scripts/generate-app-icon.swift; omit its grid,
        // backdrop and shadow, and use transparent cutouts for the central ring.
        let pin = CGMutablePath()
        pin.move(to:CGPoint(x:512,y:170))
        pin.addCurve(to:CGPoint(x:260,y:605),control1:CGPoint(x:440,y:270),control2:CGPoint(x:260,y:427))
        pin.addCurve(to:CGPoint(x:764,y:605),control1:CGPoint(x:260,y:946),control2:CGPoint(x:764,y:946))
        pin.addCurve(to:CGPoint(x:512,y:170),control1:CGPoint(x:764,y:427),control2:CGPoint(x:584,y:270))
        pin.closeSubpath()
        let bounds = pin.boundingBoxOfPath
        let shape = CGMutablePath()
        shape.addPath(pin)
        shape.addEllipse(in:CGRect(x:398,y:512,width:228,height:228))
        shape.addEllipse(in:CGRect(x:474,y:588,width:76,height:76))
        let image = NSImage(size:NSSize(width:18,height:18),flipped:false) { rect in
            guard let context = NSGraphicsContext.current?.cgContext else { return false }
            context.saveGState()
            defer { context.restoreGState() }
            let scale = min((rect.width-1)/bounds.width,(rect.height-1)/bounds.height)
            context.translateBy(x:rect.midX-bounds.midX*scale,y:rect.midY-bounds.midY*scale)
            context.scaleBy(x:scale,y:scale)
            context.addPath(shape)
            context.setFillColor(NSColor.black.cgColor)
            context.drawPath(using:.eoFill)
            return true
        }
        image.isTemplate = true
        return image
    }

    func update(state: String, description: String) {
        let next: Phase
        switch state {
        case "ready": next = .ready
        case "connecting","waiting-for-video","waiting-for-subscription": next = .preparing
        case "reporting": next = .reporting
        case "error": next = .error
        default: next = .idle
        }
        if phase != next {
            phase = next
            switch next {
            case .idle: badge.color = .systemGray
            case .preparing: badge.color = .systemOrange
            case .reporting: badge.color = .systemGreen
            case .error: badge.color = .systemRed
            case .ready: badge.color = nil
            }
        }
        button.toolTip = "toAnywhere · \(description)"
        button.setAccessibilityLabel("toAnywhere，\(description)")
        button.setAccessibilityHelp("点击查看状态和操作菜单")
    }
}

private final class StatusBadgeView: NSView {
    var color: NSColor? {
        didSet { isHidden = color == nil;needsDisplay = true }
    }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func draw(_ dirtyRect: NSRect) {
        guard let color else { return }
        let dot = NSBezierPath(ovalIn:bounds.insetBy(dx:1,dy:1))
        NSColor.windowBackgroundColor.setStroke()
        dot.lineWidth = 1.5;dot.stroke()
        color.setFill();dot.fill()
    }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance();needsDisplay = true
    }
}
