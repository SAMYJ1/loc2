import AppKit

/// Let AppKit own menu tracking, highlighting, keyboard navigation and dismissal.
final class MenuBarStatusMenu: NSObject, NSMenuDelegate {
    private var isTracking = false
    private var pendingUpdate: (() -> Void)?

    init(menu: NSMenu, statusItem: NSStatusItem) {
        super.init()
        menu.delegate = self
        statusItem.menu = menu
    }

    func update(_ action: @escaping () -> Void) {
        if isTracking { pendingUpdate = action }
        else { action() }
    }

    func menuWillOpen(_ menu: NSMenu) {
        isTracking = true
    }

    func menuDidClose(_ menu: NSMenu) {
        isTracking = false
        let update = pendingUpdate
        pendingUpdate = nil
        // Apply status changes after AppKit finishes closing the menu.
        if let update { DispatchQueue.main.async(execute:update) }
    }
}
