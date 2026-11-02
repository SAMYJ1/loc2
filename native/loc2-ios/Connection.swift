import Foundation
import Security
import CryptoKit

final class SecureProfile {
    private static let service = "local.loc2.mobile.connection"
    static func read() throws -> ComputerRegistry {
        let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,
                                  kSecReturnData as String:true,kSecMatchLimit as String:kSecMatchLimitOne]
        var item: CFTypeRef?
        let result = SecItemCopyMatching(query as CFDictionary,&item)
        if result == errSecItemNotFound { return ComputerRegistry() }
        guard result == errSecSuccess,let data = item as? Data else { throw AppFailure("无法读取已配对电脑，原钥匙串记录已保留") }
        return try ComputerRegistry.decode(data)
    }
    static func save(_ registry: ComputerRegistry) throws {
        let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service]
        let data = try JSONEncoder().encode(registry)
        let update = SecItemUpdate(query as CFDictionary,[kSecValueData as String:data] as CFDictionary)
        if update == errSecSuccess { return }
        guard update == errSecItemNotFound else { throw AppFailure("无法安全保存连接授权") }
        var insert = query
        insert[kSecValueData as String] = data
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(insert as CFDictionary,nil) == errSecSuccess else { throw AppFailure("无法安全保存连接授权") }
    }
}

enum ControlRoute: String,Sendable { case automatic,usb,network }

final class PinnedConnection: NSObject, URLSessionDelegate, URLSessionTaskDelegate, @unchecked Sendable {
    let profile: ServerProfile
    let route: ControlRoute
    private let usb: USBControlTunnel?
    private var session: URLSession!
    private let failureLock = NSLock()
    private var validationFailure: String?
    private func recordFailure(_ value:String?) { failureLock.lock();validationFailure = value;failureLock.unlock() }
    private func recordedFailure() -> String? { failureLock.lock();defer { failureLock.unlock() };return validationFailure }
    init(_ profile: ServerProfile,usb: USBControlTunnel? = .shared,route: ControlRoute = .automatic) {
        self.profile = profile
        self.usb = usb
        self.route = route
        super.init()
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 12
        config.httpCookieStorage = nil
        config.urlCredentialStorage = nil
        config.urlCache = nil
        session = URLSession(configuration:config,delegate:self,delegateQueue:nil)
    }
    func close() { session.invalidateAndCancel() }
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let expectedHost = URL(string:profile.endpoint)?.host,
              challenge.protectionSpace.host.lowercased() == expectedHost.lowercased() || usb?.acceptsTLSHost(challenge.protectionSpace.host,port:challenge.protectionSpace.port) == true,
              let trust = challenge.protectionSpace.serverTrust,
              let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate], let certificate = chain.first else {
            recordFailure("连接主机与邀请不一致，无法校验 Mac 身份")
            completionHandler(.cancelAuthenticationChallenge,nil); return
        }
        let bytes = SecCertificateCopyData(certificate) as Data
        let digest = SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined()
        guard digest == profile.fingerprint.lowercased() else { recordFailure("Mac 的服务身份已变化，请重新扫码确认");completionHandler(.cancelAuthenticationChallenge,nil); return }
        // The USB loopback relay changes the socket address, never the trusted Mac identity.
        SecTrustSetPolicies(trust,SecPolicyCreateSSL(true,expectedHost as CFString))
        // A physically scanned certificate is our explicit local trust anchor.
        SecTrustSetAnchorCertificates(trust,[certificate] as CFArray)
        SecTrustSetAnchorCertificatesOnly(trust,true)
        guard SecTrustEvaluateWithError(trust,nil) else { recordFailure("Mac 服务证书未通过校验，请检查系统时间和服务配置");completionHandler(.cancelAuthenticationChallenge,nil); return }
        recordFailure(nil)
        completionHandler(.useCredential,URLCredential(trust:trust))
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
    func request(_ path: String, body: [String:Any]? = nil,timeout: TimeInterval? = nil) async throws -> [String:Any] {
        let usbEndpoint = route == .network ? nil : usb?.endpoint
        if route == .usb && usbEndpoint == nil { throw AppFailure("USB 连接暂不可用") }
        guard let url = URL(string:(usbEndpoint ?? profile.endpoint) + path) else { throw AppFailure("服务地址无效") }
        var request = URLRequest(url:url)
        if let timeout { request.timeoutInterval = timeout }
        if let token = profile.token { request.setValue("Bearer " + token,forHTTPHeaderField:"Authorization") }
        if let body {
            request.httpMethod = "POST"
            request.setValue("application/json",forHTTPHeaderField:"Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject:body)
        }
        let data: Data, response: URLResponse
        do { (data,response) = try await session.data(for:request) }
        catch {
            if Task.isCancelled { throw CancellationError() }
            if let reason = recordedFailure() { throw AppFailure(reason,identityFailure:true) }
            throw error
        }
        guard data.count <= 262144, let http = response as? HTTPURLResponse,
              var value = try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw AppFailure("服务响应无效") }
        guard http.statusCode == 200, value["ok"] as? Bool == true else {
            throw AppFailure(value["error"] as? String ?? "请求未完成",statusCode:http.statusCode)
        }
        value["controlTransport"] = usbEndpoint == nil ? "network" : "usb"
        return value
    }
}
