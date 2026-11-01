import Foundation
import Security

final class CredentialFixture: WiFiCredentialStorage {
    var saved: [String:String] = [:]
    var system: [String:String] = ["network-a":"fixture-a", "network-b":"fixture-b"]
    var reads: [(String,Bool)] = []
    var readFailure: OSStatus?
    var saveFailure: OSStatus?
    func savedPassword(for ssid: String) throws -> String? {
        if let readFailure { throw WiFiCredentialFailure(status: readFailure) }
        return saved[ssid]
    }
    func systemPassword(for ssid: String, interactive: Bool) throws -> String {
        reads.append((ssid,interactive))
        guard let value = system[ssid] else { throw WiFiCredentialFailure(status: errSecItemNotFound) }
        return value
    }
    func savePassword(_ password: String, for ssid: String) throws {
        if let saveFailure { throw WiFiCredentialFailure(status: saveFailure) }
        saved[ssid] = password
    }
}

@main struct WiFiCredentialProbe {
    static func main() throws {
        let fixture = CredentialFixture()
        let first = WiFiCredentials(storage:fixture)
        let initial = try first.password(for:"network-a",interactive:true)
        precondition(initial == "fixture-a")
        // A later process has no in-memory credentials and cannot read the system item.
        fixture.system.removeValue(forKey:"network-a")
        let restarted = WiFiCredentials(storage:fixture)
        for _ in 0..<3 {
            let value = try restarted.password(for:"network-a",interactive:false)
            precondition(value == "fixture-a", "Previously initialized network must survive process restart")
        }
        precondition(fixture.reads.count == 1, "Daily connections must not reread the protected system item")
        let other = try restarted.password(for:"network-b",interactive:false)
        precondition(other == "fixture-b" && fixture.reads.last?.1 == false)
        fixture.system["network-a"] = "updated-fixture"
        let refreshed = try restarted.password(for:"network-a",interactive:true)
        precondition(refreshed == "updated-fixture" && fixture.saved["network-a"] == refreshed)
        precondition(fixture.saved["network-b"] == "fixture-b")
        fixture.readFailure = errSecInteractionNotAllowed
        let reads = fixture.reads.count
        do {
            _ = try restarted.password(for:"network-a",interactive:false)
            preconditionFailure("Locked keychain must not be bypassed")
        } catch let error as WiFiCredentialFailure {
            precondition(error.status == errSecInteractionNotAllowed)
        }
        precondition(fixture.reads.count == reads && fixture.saved["network-a"] == "updated-fixture")
        print("PASS: initialized credentials survive restart, network isolation, explicit refresh, locked-keychain handling")
    }
}
