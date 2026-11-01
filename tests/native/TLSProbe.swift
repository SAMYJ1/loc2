import Foundation
import Security
import CryptoKit
@main struct TLSProbe {
    static func main() async {
        do {
            let file = CommandLine.arguments[1]
            let correct = try JSONDecoder().decode(ServerProfile.self,from:Data(contentsOf:URL(fileURLWithPath:file)))
            for negative in [false,true] {
                var profile = correct
                if negative { profile.fingerprint = String(repeating:"0",count:64) }
                let connection = PinnedConnection(profile)
                do {
                    _ = try await connection.request("/v1/status")
                    connection.close();throw AppFailure("Unauthenticated request unexpectedly succeeded")
                } catch let error as AppFailure {
                    connection.close()
                    guard negative ? error.message.contains("身份已变化") : error.message.contains("配对授权") else { throw AppFailure("TLS verdict mismatch") }
                } catch {
                    connection.close()
                    guard negative else { throw error }
                }
            }
            print("PASS: mixed-case hostname and pinned certificate accepted; wrong pin rejected")
        } catch { print("FAIL:",error.localizedDescription);exit(1) }
    }
}
