# 本机运行时补丁

`wpa3-transition.patch` 基于本机既有 MacPlay／LIVI 源码副本，保留其 GPL 来源与许可；上游为 [Roylyl/MacPlay](https://github.com/Roylyl/MacPlay)。补丁只包含源码和合成测试，不包含运行时二进制、认证资料、设备标识或凭据。

补丁增加显式的同网模式：关闭旧 WiFiSharing 配置消息，仍通过 CarPlayStartSession 传递经当前接入点扫描确认的 transition 参数。默认模式和 USB 行为保留。不能仅通过修改网络安全类型来替代该补丁。

在匹配基线的 helper 源码根目录应用补丁后，使用：

```sh
cargo test --locked -p livi-runtime --lib --test bringup
cargo build --locked --release -p livi-helperd
```

基线文件摘要、已测试 helper 摘要与补丁摘要见 [manifest](../../docs/native-runtime-manifest-2026-11-02.json)。本机既有源码含此前的无线地址、订阅和会话修正，不保证能直接应用到任意上游版本。

运行时的 `resources/driver/loc2-capabilities.json` 必须声明 `schemaVersion: 1`、`wpa3Transition: true`，并以 `helperSHA256` 绑定实际安装的 helper；应用在启动前核对摘要。声明用于防止新应用误配旧 helper，不代替设备验收。重建后的二进制若摘要改变，应重新验证后再更新声明。

当前已验证的是一台 iPhone、一个 WPA2/WPA3 混合接入点；仅 WPA3 模式没有放行。完整行为与限制见[验收记录](../../docs/native-app-validation-2026-10-31.md)。
