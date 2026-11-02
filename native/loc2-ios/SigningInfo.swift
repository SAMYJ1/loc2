import Foundation

enum SigningInfo {
    static var expiration: Date? {
        guard let url = Bundle.main.url(forResource:"embedded",withExtension:"mobileprovision"),
              let data = try? Data(contentsOf:url),
              let start = data.range(of:Data("<?xml".utf8)),
              let end = data.range(of:Data("</plist>".utf8),in:start.lowerBound..<data.endIndex),
              let plist = try? PropertyListSerialization.propertyList(from:Data(data[start.lowerBound..<end.upperBound]),format:nil),
              let values = plist as? [String:Any] else { return nil }
        return values["ExpirationDate"] as? Date
    }
    static var expiryText: String {
        #if targetEnvironment(simulator)
        return "模拟器构建，无需设备签名"
        #else
        return expiration?.formatted(date:.numeric,time:.shortened) ?? "请在 Mac 安装记录中查看"
        #endif
    }
}
