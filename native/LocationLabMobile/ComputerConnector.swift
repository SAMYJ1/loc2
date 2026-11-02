import Foundation

final class ComputerConnection: @unchecked Sendable {
    let client: PinnedConnection
    let status: [String:Any]
    init(client: PinnedConnection,status: [String:Any]) { self.client = client;self.status = status }
}

/// Discovers with GET /status only. Mutating requests never enter this retry loop.
final class ComputerConnector: @unchecked Sendable {
    private let usb: USBControlTunnel?
    private let timeout: TimeInterval
    init(usb: USBControlTunnel? = .shared,timeout: TimeInterval = 2) { self.usb = usb;self.timeout = timeout }

    private func probe(_ profile: ServerProfile,route: ControlRoute,requireDevice: Bool = true) async -> ComputerConnection? {
        guard !Task.isCancelled else { return nil }
        let client = PinnedConnection(profile,usb:usb,route:route)
        do {
            let value = try await client.request("/v1/status",timeout:timeout)
            let snapshot = SessionSnapshot(value)
            let devices = (value["status"] as? [String:Any])?["availableDevices"] as? [String] ?? []
            guard !Task.isCancelled,value["authorized"] as? Bool == true,
                  !snapshot.epoch.isEmpty,!requireDevice || snapshot.sessionID != nil || devices.contains(snapshot.deviceID) else { client.close();return nil }
            return ComputerConnection(client:client,status:value)
        } catch { client.close();return nil }
    }
    private func race(_ profiles: [ServerProfile],route: ControlRoute) async -> ComputerConnection? {
        await withTaskGroup(of:ComputerConnection?.self) { group in
            let initial = min(4,profiles.count)
            for profile in profiles.prefix(initial) { group.addTask { await self.probe(profile,route:route) } }
            var next = initial
            var winner: ComputerConnection?
            for await candidate in group {
                if let candidate {
                    if winner == nil && !Task.isCancelled { winner = candidate;group.cancelAll() }
                    else { candidate.client.close() }
                }
                if winner == nil && !Task.isCancelled && next < profiles.count {
                    let profile = profiles[next];next += 1
                    group.addTask { await self.probe(profile,route:route) }
                }
            }
            return winner
        }
    }
    func connect(_ profile: ServerProfile) async -> ComputerConnection? {
        if usb?.endpoint != nil,let result = await probe(profile,route:.usb,requireDevice:false) { return result }
        return await probe(profile,route:.network,requireDevice:false)
    }
    func discover(_ profiles: [ServerProfile],currentID: String?,sessionOwnerID: String?) async -> ComputerConnection? {
        // A reachable Mac that is already reporting keeps ownership until stopped.
        if let owner = profiles.first(where:{ $0.id == sessionOwnerID }),let result = await connect(owner) { return result }
        if usb?.endpoint != nil,let result = await race(profiles,route:.usb) { return result }
        if let current = profiles.first(where:{ $0.id == currentID }),current.id != sessionOwnerID,
           let result = await probe(current,route:.network) { return result }
        let others = profiles.filter { $0.id != currentID && $0.id != sessionOwnerID }
        return await race(others,route:.network)
    }
    func pairingConnection(_ profile: ServerProfile) async throws -> PinnedConnection {
        // Identify the route using a read before sending the one-time pairing request.
        let routes: [ControlRoute] = usb?.endpoint == nil ? [.network] : [.usb,.network]
        var last: Error = AppFailure("无法联系这台 Mac")
        for route in routes {
            try Task.checkCancellation()
            let client = PinnedConnection(profile,usb:usb,route:route)
            do {
                _ = try await client.request("/v1/status",timeout:timeout)
                return client
            } catch let error as AppFailure where error.statusCode == 401 { return client }
            catch { client.close();last = error }
        }
        throw last
    }
}
