import Foundation
import Network

/// Loopback-only USB relay. URLSession still performs the end-to-end pinned TLS.
final class USBControlTunnel: @unchecked Sendable {
    static let shared = USBControlTunnel()
    private let devicePort: UInt16
    private let queue = DispatchQueue(label:"loc2.usb-control")
    private let lock = NSLock()
    private var proxyPort: UInt16?
    private var connected = false
    private var lastConnected = -Double.infinity
    private var enabled = false
    private var generation = 0
    private var usbListener: NWListener?
    private var proxyListener: NWListener?
    private var connections: [ObjectIdentifier:NWConnection] = [:]
    private var usbIDs = Set<ObjectIdentifier>()
    private var readyIDs = Set<ObjectIdentifier>()
    private var pendingUSB: [NWConnection] = []
    private var pendingClients: [NWConnection] = []
    private var partners: [ObjectIdentifier:ObjectIdentifier] = [:]
    var onAvailabilityChange: (@MainActor () -> Void)?
    init(devicePort: UInt16 = 32145) { self.devicePort = devicePort }

    var endpoint: String? {
        lock.lock();defer { lock.unlock() }
        // A completed HTTP request consumes one reverse stream. Keep selecting
        // USB briefly while the Mac replenishes its pool, rather than leaking
        // the next command onto a different route between consecutive requests.
        guard connected || ProcessInfo.processInfo.systemUptime-lastConnected<2,let proxyPort else { return nil }
        return "https://127.0.0.1:\(proxyPort)"
    }
    func acceptsTLSHost(_ host: String,port: Int) -> Bool {
        lock.lock();defer { lock.unlock() }
        return host == "127.0.0.1" && proxyPort.map { Int($0) == port } == true
    }
    func start() { queue.async { if !self.enabled { self.enabled = true;self.listen() } } }
    func stop() { queue.async { self.enabled = false;self.clear() } }
    private func publish() {
        let newPort = proxyListener?.port?.rawValue
        let available = !usbIDs.intersection(readyIDs).isEmpty
        lock.lock();let changed = connected != available || proxyPort != newPort
        if available { lastConnected = ProcessInfo.processInfo.systemUptime }
        if newPort == nil { lastConnected = -Double.infinity }
        connected = available;proxyPort = newPort;lock.unlock()
        if changed { DispatchQueue.main.async { self.onAvailabilityChange?() } }
    }
    private func clear() {
        generation += 1
        usbListener?.cancel();proxyListener?.cancel();usbListener = nil;proxyListener = nil
        let old = Array(connections.values)
        connections.removeAll();usbIDs.removeAll();readyIDs.removeAll()
        pendingUSB.removeAll();pendingClients.removeAll();partners.removeAll()
        old.forEach { $0.cancel() };publish()
    }
    private func listener(port: UInt16) throws -> NWListener {
        let parameters = NWParameters.tcp
        parameters.allowLocalEndpointReuse = true
        parameters.requiredLocalEndpoint = .hostPort(host:"127.0.0.1",port:NWEndpoint.Port(rawValue:port)!)
        return try NWListener(using:parameters)
    }
    private func listen() {
        clear();let version = generation
        do {
            let usb = try listener(port:devicePort)
            let proxy = try listener(port:0)
            usbListener = usb;proxyListener = proxy
            usb.newConnectionHandler = { [weak self] in self?.accept($0,usb:true,version:version) }
            proxy.newConnectionHandler = { [weak self] in self?.accept($0,usb:false,version:version) }
            for listener in [usb,proxy] {
                listener.stateUpdateHandler = { [weak self] state in
                    guard let self,self.generation == version,self.enabled else { return }
                    switch state {
                    case .ready: self.publish()
                    case .failed: self.retry(version:version)
                    default: break
                    }
                }
                listener.start(queue:queue)
            }
        } catch { retry(version:version) }
    }
    private func retry(version: Int) {
        guard generation == version,enabled else { return }
        clear();let next = generation
        queue.asyncAfter(deadline:.now()+2) { [weak self] in
            guard let self,self.enabled,self.generation == next else { return };self.listen()
        }
    }
    private func accept(_ connection: NWConnection,usb: Bool,version: Int) {
        guard enabled,generation == version,connections.count < 16 else { connection.cancel();return }
        let id = ObjectIdentifier(connection);connections[id] = connection
        if usb { usbIDs.insert(id) }
        connection.stateUpdateHandler = { [weak self,weak connection] state in
            guard let self,let connection,self.generation == version else { return }
            switch state {
            case .ready:
                guard self.readyIDs.insert(id).inserted else { return }
                if usb { self.pendingUSB.append(connection) } else { self.pendingClients.append(connection) }
                self.pair(version:version);self.publish()
            case .failed,.cancelled: self.close(connection)
            default: break
            }
        }
        connection.start(queue:queue)
        if !usb {
            queue.asyncAfter(deadline:.now()+3) { [weak self,weak connection] in
                guard let self,let connection,self.generation == version,self.partners[id] == nil else { return }
                self.close(connection)
            }
        }
    }
    private func pair(version: Int) {
        while !pendingUSB.isEmpty && !pendingClients.isEmpty {
            let usb = pendingUSB.removeFirst(),client = pendingClients.removeFirst()
            partners[ObjectIdentifier(usb)] = ObjectIdentifier(client)
            partners[ObjectIdentifier(client)] = ObjectIdentifier(usb)
            pipe(usb,to:client,version:version);pipe(client,to:usb,version:version)
        }
    }
    private func pipe(_ source: NWConnection,to destination: NWConnection,version: Int) {
        source.receive(minimumIncompleteLength:1,maximumLength:65536) { [weak self] data,_,complete,error in
            guard let self,self.generation == version,self.connections[ObjectIdentifier(source)] != nil else { return }
            if let data,!data.isEmpty {
                destination.send(content:data,completion:.contentProcessed { [weak self] sendError in
                    guard let self,self.generation == version else { return }
                    if complete || error != nil || sendError != nil { self.close(source) }
                    else { self.pipe(source,to:destination,version:version) }
                })
            } else if complete || error != nil { self.close(source) }
            else { self.pipe(source,to:destination,version:version) }
        }
    }
    private func close(_ connection: NWConnection) {
        let id = ObjectIdentifier(connection)
        guard connections.removeValue(forKey:id) != nil else { return }
        let partner = partners.removeValue(forKey:id)
        usbIDs.remove(id);readyIDs.remove(id)
        pendingUSB.removeAll { $0 === connection };pendingClients.removeAll { $0 === connection }
        connection.cancel()
        if let partner,let other = connections[partner] { partners.removeValue(forKey:partner);close(other) }
        publish()
    }
}
