import Foundation

@main struct MultiComputerProbe {
    static func wait(_ file: URL) async throws {
        for _ in 0..<200 {
            if FileManager.default.fileExists(atPath:file.path) { return }
            try await Task.sleep(nanoseconds:50_000_000)
        }
        throw AppFailure("Fixture coordination timed out")
    }
    static func main() async {
        do {
            let folder = URL(fileURLWithPath:CommandLine.arguments[1])
            let profiles = try JSONDecoder().decode([ServerProfile].self,from:Data(contentsOf:folder.appendingPathComponent("profiles.json")))
            let a = profiles[0],b = profiles[1],unbound = profiles[2]
            let tunnel = USBControlTunnel(devicePort:UInt16(CommandLine.arguments[2])!)
            let connector = ComputerConnector(usb:tunnel,timeout:1)
            guard let paired = await connector.discover([unbound],currentID:unbound.id,sessionOwnerID:nil),
                  paired.client.profile.id == unbound.id,paired.status["targetBound"] as? Bool == false else {
                throw AppFailure("Paired Mac without a reporting target appeared offline")
            }
            paired.client.close()
            var stalled = a
            stalled.endpoint = "https://localhost:" + (try String(contentsOf:folder.appendingPathComponent("stalled-port"))).trimmingCharacters(in:.whitespacesAndNewlines)
            let began = Date()
            guard let reachable = await connector.discover([stalled,unbound,b],currentID:stalled.id,sessionOwnerID:nil),
                  reachable.client.profile.id == b.id,Date().timeIntervalSince(began)<4 else { throw AppFailure("Unresponsive Mac blocked automatic connection") }
            reachable.client.close()
            guard let reconnected = await connector.discover([stalled,unbound],currentID:stalled.id,sessionOwnerID:nil),
                  reconnected.client.profile.id == unbound.id,reconnected.status["targetBound"] as? Bool == false else {
                throw AppFailure("Offline current Mac did not fall back to an unbound paired Mac")
            }
            reconnected.client.close()
            // A revoked authorization must not prevent trying a separately authorized Mac.
            var revoked = a;revoked.token = "revoked-fixture"
            guard let authorized = await connector.discover([revoked,b],currentID:revoked.id,sessionOwnerID:nil),
                  authorized.client.profile.id == b.id else { throw AppFailure("Revoked Mac blocked fallback") }
            authorized.client.close()
            // USB physically goes to B, while the previous selected computer is A.
            tunnel.start();defer { tunnel.stop() }
            for _ in 0..<100 {
                if tunnel.endpoint != nil { break }
                try await Task.sleep(nanoseconds:100_000_000)
            }
            guard tunnel.endpoint != nil else { throw AppFailure("Fixture USB unavailable") }
            guard let usb = await connector.discover(profiles,currentID:a.id,sessionOwnerID:nil),
                  usb.client.profile.id == b.id,usb.status["controlTransport"] as? String == "usb" else { throw AppFailure("USB computer identity was not matched") }
            usb.client.close()
            let otherComputers = (0..<16).map { index -> ServerProfile in
                var value = a
                value.fingerprint = String(repeating:"c",count:60)+String(format:"%04x",index)
                value.token = "never-transmit-fixture-\(index)"
                return value
            }
            guard let many = await connector.discover(otherComputers+[b],currentID:otherComputers[0].id,sessionOwnerID:nil),
                  many.client.profile.id == b.id,many.status["controlTransport"] as? String == "usb" else { throw AppFailure("USB discovery exhausted its bounded connection pool") }
            many.client.close()
            guard let network = await connector.discover([a],currentID:a.id,sessionOwnerID:nil),
                  network.client.profile.id == a.id,network.status["controlTransport"] as? String == "network" else { throw AppFailure("Another computer's USB blocked LAN") }
            network.client.close()
            // A reachable existing session remains owned by A, even with B on USB.
            guard let owner = await connector.discover(profiles,currentID:a.id,sessionOwnerID:a.id),owner.client.profile.id == a.id else { throw AppFailure("Session owner unexpectedly changed") }
            owner.client.close()
            // Pairing probes are read-only and can identify B without an existing token.
            var invitation = b;invitation.token = nil
            let pairing = try await connector.pairingConnection(invitation)
            precondition(pairing.route == .usb);pairing.close()
            // Remove USB, then take A entirely offline. Discovery must find B via LAN.
            tunnel.stop()
            for _ in 0..<50 {
                if tunnel.endpoint == nil { break }
                try await Task.sleep(nanoseconds:50_000_000)
            }
            try Data().write(to:folder.appendingPathComponent("disable-a"))
            try await wait(folder.appendingPathComponent("a-off"))
            guard let fallback = await connector.discover(profiles,currentID:a.id,sessionOwnerID:nil),
                  fallback.client.profile.id == b.id,fallback.status["controlTransport"] as? String == "network" else { throw AppFailure("Offline Mac did not fail over") }
            defer { fallback.client.close() }
            var command = SessionSnapshot(fallback.status).command
            command["point"] = ["latitude":1.0,"longitude":2.0]
            let applied = try await fallback.client.request("/v1/apply",body:command)
            guard SessionSnapshot(applied).sessionID != nil else { throw AppFailure("Chosen computer did not accept command") }
            _ = try await fallback.client.request("/v1/stop",body:SessionSnapshot(applied).command)
            print("PASS: unbound current and cross-Mac fallback, separate credentials, USB identity matching, LAN fallback, session-owner preference and no command replay")
        } catch { print("FAIL:",error.localizedDescription);exit(1) }
    }
}
