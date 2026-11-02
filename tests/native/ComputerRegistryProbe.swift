import Foundation
import CoreLocation

@main struct ComputerRegistryProbe {
    static func main() throws {
        let a = ServerProfile(endpoint:"https://same-mac.local:8767",fingerprint:String(repeating:"a",count:64),token:"fixture-a")
        let b = ServerProfile(endpoint:a.endpoint,fingerprint:String(repeating:"b",count:64),token:"fixture-b")
        var registry = try ComputerRegistry.decode(JSONEncoder().encode(a))
        precondition(registry.profiles == [a] && registry.preferredID == a.id)
        try registry.add(b)
        precondition(registry.profiles.count == 2,"Same hostname does not mean same computer")
        registry = try ComputerRegistry.decode(JSONEncoder().encode(registry))
        precondition(registry.profiles.map(\.token) == [a.token,b.token])
        var named = a;named.name = "家里的 Mac";try registry.add(named)
        var renewed = a;renewed.token = "renewed-fixture"
        try registry.add(renewed)
        precondition(registry.profiles.count == 2 && registry.preferred?.token == renewed.token && registry.preferred?.displayName == "家里的 Mac")
        var idle = SessionSnapshot();idle.epoch = "same-epoch";idle.revision = 1
        registry.recordPendingApply(for:a,snapshot:idle)
        registry.record(idle,for:b)
        precondition(registry.unresolved(excluding:b.id).map(\.id) == [a.id],"Another Mac's idle status must not clear uncertain apply ownership")
        do { try registry.forget(a.id);preconditionFailure("Unresolved session was removed") }
        catch is AppFailure {}
        registry = try ComputerRegistry.decode(JSONEncoder().encode(registry))
        precondition(registry.sessions.first?.sessionID == nil,"Pending mutation must survive restart")
        var active = idle;active.sessionID = "session-b"
        registry.record(active,for:b)
        precondition(registry.unresolved(excluding:b.id).map(\.id) == [a.id])
        registry.record(idle,for:a)
        precondition(registry.unresolved(excluding:b.id).isEmpty)
        try registry.forget(a.id)
        precondition(registry.profiles == [b] && registry.sessions.first?.computerID == b.id && registry.legacyRecoveryID == nil)
        do {
            _ = try ComputerRegistry.decode(Data(#"{"version":99,"profiles":[]}"#.utf8))
            preconditionFailure("Corrupt registry must not silently become an empty store")
        } catch {}
        print("PASS: legacy migration, multiple identities, per-Mac credentials and durable uncertain-session ownership")
    }
}
