import Foundation
import Security

struct WiFiCredentialFailure: Error {
    let status: OSStatus
}

protocol WiFiCredentialStorage {
    func savedPassword(for ssid: String) throws -> String?
    func systemPassword(for ssid: String, interactive: Bool) throws -> String
    func savePassword(_ password: String, for ssid: String) throws
}

final class WiFiCredentials {
    private let storage: WiFiCredentialStorage
    init(storage: WiFiCredentialStorage) { self.storage = storage }

    func password(for ssid: String, interactive: Bool) throws -> String {
        if !interactive, let saved = try storage.savedPassword(for:ssid) { return saved }
        let password = try storage.systemPassword(for:ssid,interactive:interactive)
        try storage.savePassword(password,for:ssid)
        return password
    }
}

/// App-owned entries in the user's default keychain. Never edits system Wi-Fi ACLs.
final class KeychainWiFiStorage: WiFiCredentialStorage {
    private static let interactionLock = NSLock()
    private let service: String
    init(service: String = "local.location-lab.wifi-credentials") { self.service = service }

    private func withInteraction<T>(_ interactive: Bool, _ body: () throws -> T) throws -> T {
        Self.interactionLock.lock()
        defer { Self.interactionLock.unlock() }
        var previous = DarwinBoolean(false)
        try check(SecKeychainGetUserInteractionAllowed(&previous))
        // kSecUseAuthenticationUIFail alone does not suppress file-keychain prompts.
        try check(SecKeychainSetUserInteractionAllowed(interactive))
        defer { SecKeychainSetUserInteractionAllowed(previous.boolValue) }
        return try body()
    }

    private func check(_ status: OSStatus) throws {
        if status != errSecSuccess { throw WiFiCredentialFailure(status:status) }
    }

    private func userKeychain() throws -> SecKeychain {
        var keychain: SecKeychain?
        try check(SecKeychainCopyDefault(&keychain))
        guard let keychain else { throw WiFiCredentialFailure(status:errSecNoSuchKeychain) }
        return keychain
    }

    private func query(_ ssid: String, keychain: SecKeychain) -> [String:Any] {
        [kSecClass as String:kSecClassGenericPassword,
         kSecAttrService as String:service,kSecAttrAccount as String:ssid,
         kSecMatchSearchList as String:[keychain]]
    }

    private func password(_ query: [String:Any]) throws -> String? {
        var query = query
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let result = SecItemCopyMatching(query as CFDictionary,&item)
        if result == errSecItemNotFound { return nil }
        try check(result)
        guard let data = item as? Data,let value = String(data:data,encoding:.utf8),!value.isEmpty else {
            throw WiFiCredentialFailure(status:errSecDecode)
        }
        return value
    }

    func savedPassword(for ssid: String) throws -> String? {
        try withInteraction(false) { try password(query(ssid,keychain:userKeychain())) }
    }

    func systemPassword(for ssid: String, interactive: Bool) throws -> String {
        try withInteraction(interactive) {
            var query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,
                                      kSecAttrService as String:"AirPort",kSecAttrAccount as String:ssid]
            if let value = try password(query) { return value }
            var system: SecKeychain?
            try check(SecKeychainOpen("/Library/Keychains/System.keychain",&system))
            guard let system else { throw WiFiCredentialFailure(status:errSecNoSuchKeychain) }
            query[kSecMatchSearchList as String] = [system]
            guard let value = try password(query) else { throw WiFiCredentialFailure(status:errSecItemNotFound) }
            return value
        }
    }

    func savePassword(_ password: String, for ssid: String) throws {
        try withInteraction(false) {
            let keychain = try userKeychain()
            let match = query(ssid,keychain:keychain)
            let data = Data(password.utf8)
            let result = SecItemUpdate(match as CFDictionary,[kSecValueData as String:data] as CFDictionary)
            if result == errSecSuccess { return }
            guard result == errSecItemNotFound else { throw WiFiCredentialFailure(status:result) }
            let insert: [String:Any] = [kSecClass as String:kSecClassGenericPassword,
                                       kSecAttrService as String:service,kSecAttrAccount as String:ssid,
                                       kSecUseKeychain as String:keychain,kSecValueData as String:data,
                                       kSecAttrLabel as String:"Location Lab · Wi-Fi"]
            try check(SecItemAdd(insert as CFDictionary,nil))
        }
    }
}
