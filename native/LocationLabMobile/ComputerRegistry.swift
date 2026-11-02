import Foundation

struct ComputerSessionRecord: Codable,Equatable {
    var computerID: String
    var epoch: String
    var sessionID: String?
}

struct ComputerRegistry: Codable,Equatable {
    var version = 2
    var profiles: [ServerProfile] = []
    var preferredID: String?
    var sessions: [ComputerSessionRecord] = []
    var legacyRecoveryID: String?

    private static func valid(_ profile: ServerProfile) -> Bool {
        guard let url = URLComponents(string:profile.endpoint) else { return false }
        return url.scheme == "https" && url.host != nil && url.user == nil && url.password == nil &&
            url.path.isEmpty && url.query == nil && url.fragment == nil && profile.fingerprint.count == 64 &&
            profile.fingerprint.allSatisfy(\.isHexDigit) && profile.token?.isEmpty == false && (profile.token?.count ?? 0)<=128
    }

    static func decode(_ data: Data) throws -> ComputerRegistry {
        let decoder = JSONDecoder()
        guard let object = try JSONSerialization.jsonObject(with:data) as? [String:Any] else {
            throw AppFailure("已配对电脑资料无法读取，原记录已保留")
        }
        let value: ComputerRegistry
        if object["profiles"] != nil || object["version"] != nil {
            value = try decoder.decode(ComputerRegistry.self,from:data)
        } else {
            let legacy = try decoder.decode(ServerProfile.self,from:data)
            value = ComputerRegistry(profiles:[legacy],preferredID:legacy.id,legacyRecoveryID:legacy.id)
        }
        guard value.version == 2,Set(value.profiles.map(\.id)).count == value.profiles.count,
              Set(value.sessions.map(\.computerID)).count == value.sessions.count,
              value.profiles.allSatisfy(Self.valid),value.sessions.allSatisfy({ record in value.profiles.contains { $0.id == record.computerID } }) else {
            throw AppFailure("已配对电脑资料无效，原记录已保留")
        }
        return value
    }
    var preferred: ServerProfile? { profiles.first { $0.id == preferredID } ?? profiles.first }
    mutating func add(_ profile: ServerProfile) throws {
        guard Self.valid(profile) else { throw AppFailure("电脑连接资料无效，未保存") }
        var saved = profile
        saved.name = profile.name ?? profiles.first(where:{ $0.id == profile.id })?.name
        // Two computers can use the same hostname on different networks.
        // Only a previously approved certificate identity denotes the same Mac.
        profiles.removeAll { $0.id == profile.id }
        profiles.append(saved);preferredID = saved.id
    }
    mutating func forget(_ id: String) throws {
        guard !sessions.contains(where:{ $0.computerID == id }) else { throw AppFailure("请先确认该电脑已停止报点，再移除连接") }
        profiles.removeAll { $0.id == id }
        if legacyRecoveryID == id { legacyRecoveryID = nil }
        if preferredID == id { preferredID = profiles.first?.id }
    }
    mutating func record(_ snapshot: SessionSnapshot,for profile: ServerProfile) {
        sessions.removeAll { $0.computerID == profile.id }
        if let session = snapshot.sessionID { sessions.append(.init(computerID:profile.id,epoch:snapshot.epoch,sessionID:session)) }
    }
    mutating func recordPendingApply(for profile: ServerProfile,snapshot: SessionSnapshot) {
        sessions.removeAll { $0.computerID == profile.id }
        sessions.append(.init(computerID:profile.id,epoch:snapshot.epoch,sessionID:snapshot.sessionID))
    }
    func unresolved(excluding currentID: String?) -> [ServerProfile] {
        profiles.filter { profile in profile.id != currentID && sessions.contains { $0.computerID == profile.id } }
    }
}
