import Foundation

@main struct USBControlProbe {
    static func main() async {
        do {
            let file = CommandLine.arguments[1]
            let port = UInt16(CommandLine.arguments[2])!
            let profile = try JSONDecoder().decode(ServerProfile.self,from:Data(contentsOf:URL(fileURLWithPath:file)))
            let tunnel = USBControlTunnel(devicePort:port)
            tunnel.start();defer { tunnel.stop() }
            for _ in 0..<100 {
                if tunnel.endpoint != nil { break }
                try await Task.sleep(nanoseconds:100_000_000)
            }
            guard tunnel.endpoint != nil else { throw AppFailure("USB relay did not become available") }
            let client = PinnedConnection(profile,usb:tunnel);defer { client.close() }
            let status = try await client.request("/v1/status")
            guard status["controlTransport"] as? String == "usb",status["authorized"] as? Bool == true else { throw AppFailure("USB status failed") }
            var command = SessionSnapshot(status).command
            command["point"] = ["latitude":1.0,"longitude":2.0]
            let applied = try await client.request("/v1/apply",body:command)
            guard SessionSnapshot(applied).sessionID != nil else { throw AppFailure("USB apply failed") }
            do {
                _ = try await client.request("/v1/apply",body:command)
                throw AppFailure("Replay unexpectedly succeeded")
            } catch let error as AppFailure {
                guard error.message.contains("请求已处理") else { throw error }
            }
            let stopped = try await client.request("/v1/stop",body:SessionSnapshot(applied).command)
            guard SessionSnapshot(stopped).sessionID == nil else { throw AppFailure("USB stop failed") }
            var wrongPin = profile;wrongPin.fingerprint = String(repeating:"0",count:64)
            let bad = PinnedConnection(wrongPin,usb:tunnel);defer { bad.close() }
            do {
                _ = try await bad.request("/v1/status")
                throw AppFailure("Wrong pin unexpectedly succeeded")
            } catch let error as AppFailure {
                guard error.message.contains("身份已变化") else { throw error }
            }
            var wrongHost = profile;wrongHost.endpoint = "https://unrelated-fixture.invalid:9"
            let wrongName = PinnedConnection(wrongHost,usb:tunnel);defer { wrongName.close() }
            do {
                _ = try await wrongName.request("/v1/status")
                throw AppFailure("Wrong certificate hostname unexpectedly succeeded")
            } catch let error as AppFailure {
                guard error.message.contains("证书未通过校验") else { throw error }
            }
            var wrongToken = profile;wrongToken.token = "unrecognized-fixture-token"
            let unauthorized = PinnedConnection(wrongToken,usb:tunnel);defer { unauthorized.close() }
            do {
                _ = try await unauthorized.request("/v1/status")
                throw AppFailure("Wrong token unexpectedly succeeded")
            } catch let error as AppFailure {
                guard error.message.contains("配对授权") else { throw error }
            }
            print("PASS: USB relay with unreachable LAN endpoint, real pinned TLS, authorization, apply/stop and replay rejection")
        } catch { print("FAIL:",error.localizedDescription);exit(1) }
    }
}
