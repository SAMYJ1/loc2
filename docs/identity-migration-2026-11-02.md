# Loc2 标识与数据迁移

2026-11-02，按用户要求统一产品名称、源码路径和签名标识。显示名称为 **Loc2**，技术标识使用小写 `loc2`。

| 项目 | 当前值 |
| --- | --- |
| 仓库／目录 | `SAMYJ1/loc2`、`/Users/eugene/code/loc2` |
| Python 包与入口 | `loc2`、`python3 -m loc2.local_host` |
| Mac 源码／产物 | `native/loc2-mac`、`build/Loc2.app` |
| iPhone 工程／scheme | `native/loc2-ios/loc2.xcodeproj`、`loc2` |
| Mac bundle ID | `local.loc2.app` |
| iPhone bundle ID | `local.loc2.mobile` |
| 配对 URL scheme | `loc2://pair` |
| Bonjour 类型 | `_loc2._tcp.` |
| Mac Wi-Fi 钥匙串服务 | `local.loc2.wifi-credentials` |
| iPhone 配对钥匙串服务 | `local.loc2.mobile.connection` |
| Mac 配置／运行时 | `~/.config/loc2`、`~/Library/Application Support/loc2` |
| 运行时能力声明 | `resources/driver/loc2-capabilities.json` |

开发者团队和证书继续使用原账号，应用的签名 identifier、iPhone application identifier 和 keychain access group 使用新 bundle ID。新服务生成了新的 TLS 身份，迁移时只更新本机 Mac 对应的证书指纹；授权令牌和其他电脑记录不被替换，身份校验没有放宽。

## 数据保全与安装

- 迁移前备份源码、配置、两端签名 App，以及手机的 Library／Documents 和应用专属钥匙串数据。
- Mac 的 2 条应用专属网络凭据通过私有 FIFO 在进程内存中转移，新钥匙串服务写入后读回核对。
- iPhone 迁移回执确认：1 台电脑、11 条最近地点、0 个收藏和已有选点草稿。安装最终普通版本后，地点文件与备份逐字节一致。
- 新 bundle ID 被系统视为另一个 App。免费开发签名安装数量上限阻止并存；在用户明确确认后，仅卸载旧版本，再安装 Loc2 并导入备份，未移除其他 App。
- 临时导出／导入代码均位于项目外，最终构建不包含迁移桥接代码。回退备份与 Git 历史保留，不作为当前产品配置。
- 定位服务快捷指令改用新名称，需要在 App 内重新添加；不会把旧名称继续作为新版本的默认配置。

## 验证

- Python 87 项测试通过。
- 原生 TLS、USB 控制和多电脑集成检查通过。
- 四组网页流程通过：配对控制、持久授权、收藏、合成地图 SDK 场景。
- Mac 与 iPhone 构建、签名和安装检查通过。
- 生产 Swift TLS 客户端使用迁移后的授权，成功读取真实 Loc2 服务状态；未发送应用位置或停止请求。
- 当前源码、路径及配置的旧产品名扫描为零；第三方运行时及其许可归属保持原状。

菜单栏使用 macOS 原生 `NSMenu`，由系统处理悬停高亮、键盘选择及展开／关闭；展开时暂缓状态内容更新，关闭后应用最新状态。用户已现场确认菜单交互可用。
