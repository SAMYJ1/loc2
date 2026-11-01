import Foundation
import Security

@main struct KeychainRoundTripProbe {
    static func main() throws {
        let args = CommandLine.arguments
        precondition(args.count == 3 && UUID(uuidString:args[2]) != nil)
        let service = "local.location-lab.tests." + args[2]
        let storage = KeychainWiFiStorage(service:service)
        switch args[1] {
        case "write": try storage.savePassword("not-a-real-credential",for:"fixture-network")
        case "read":
            let value = try storage.savedPassword(for:"fixture-network")
            precondition(value == "not-a-real-credential")
        case "delete":
            var keychain: SecKeychain?
            precondition(SecKeychainCopyDefault(&keychain) == errSecSuccess)
            guard let keychain else { preconditionFailure("User keychain unavailable") }
            let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,
                                      kSecAttrService as String:service,kSecAttrAccount as String:"fixture-network",
                                      kSecMatchSearchList as String:[keychain]]
            precondition(SecItemDelete(query as CFDictionary) == errSecSuccess)
        default: preconditionFailure("Unknown test action")
        }
        print("PASS: keychain fixture " + args[1])
    }
}
