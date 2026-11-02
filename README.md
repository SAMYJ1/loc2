# Loc2

Loc2 是一个个人使用的 iPhone 定位控制工具，由 iPhone 原生 App 和 Mac 菜单栏后台组成。用户在 iPhone 上通过 Apple 地图搜索、长按选点或输入明确的 WGS84 坐标；只有点击“应用位置”后，Mac 才会通过已配置的 USB 或无线运行时向绑定的 iPhone 提供位置。

核心行为：

- 支持 USB 与无线报点；配置为双通道时优先 USB，未接 USB 时使用无线。
- 一台 iPhone 可以保存多台 Mac，自动寻找可用的已配对电脑。
- 选点只更新草稿，不会自动开始报点；断线、重启或切换电脑也不会重放旧目标。
- 停止报点与确认恢复真实位置是两个独立步骤。
- 手机与 Mac 使用 TLS、二维码授权和目标绑定；同一局域网不等于自动信任。

Loc2 不能保证 iOS 接受任意距离的目标。设备可能根据当前系统状态筛选外部位置，因此必须以手机上的实际观察为准，不能只看 Mac 的发送计数。

## 系统要求

- 完整 Mac Release：Apple Silicon，macOS 26.0 或更新版本。
- iPhone App：iOS 17.0 或更新版本，当前 IPA 为开发签名，设备需包含在描述文件中并开启 Developer Mode。
- 首次扫码和无线控制：Mac 与 iPhone 位于同一局域网，Mac 有可用的私有 IPv4 地址。
- 无线报点：Mac 和 iPhone 已完成系统蓝牙配对，并能访问当前 Wi-Fi 的授权信息。
- 运行时认证材料：用户有权使用的 `identity.pk8` 和 `certificate.p7b`。

完整 Mac Release 已包含运行时程序和 Python，但不会包含私钥、运行时认证材料、旧电脑的 TLS 身份、扫码授权或 Wi-Fi 凭据。当前 Mac 包使用开发签名且尚未 notarize；安装前应核对 Release 提供的 SHA-256 和代码签名，不要通过移除安全属性绕过来源检查。

## 安装

从 [GitHub Releases](https://github.com/SAMYJ1/loc2/releases) 下载对应版本：

1. 核对 `SHA256SUMS` 和发布元数据。
2. 解压 macOS ZIP，将 `Loc2.app` 放入 `/Applications` 后正常打开。
3. 用 Xcode 或 Apple Configurator 将开发签名 IPA 安装到描述文件包含的 iPhone。
4. 完成下方“新 Mac 首次设置”。安装 App 本身不会开始报点。

发布包限制、签名和打包方法见[应用 Release](docs/releases.md)。

<<<<<<< HEAD
## 新 Mac 首次设置
=======
Mac App ZIP 与 iOS 开发签名 IPA 通过 [GitHub Releases](https://github.com/SAMYJ1/loc2/releases) 分发。Mac 完整包包含运行时与 Python，无需手填运行时路径；认证材料支持在 App 内登录 GitHub，从指定私有仓库一键下载并导入。平台要求、签名限制及打包方法见[应用 Release](docs/releases.md)。
>>>>>>> aab7ab4 (feat: sign in to GitHub and import private authentication in app)

以下配置是每台 Mac 独立的。不能只安装 App 和扫码；运行时认证、地图校准、目标绑定和网络授权都完成后，原生地图选点才能正常应用。

### 1. 首次启动 Mac App

打开 Loc2 后，应用会创建 `~/.config/loc2`，生成这台 Mac 独立的 TLS 身份，并在默认端口 `8767` 启动手机控制服务。

默认情况下，Loc2 根据 macOS 默认路由自动选择网络接口，并在默认路由变化时重新绑定。不要从另一台 Mac 复制 `en0`、`en1` 或 `wifiInterface`。只有确实需要固定多网卡中的某个接口时，才显式设置 `nativePhone.interface`。

### 2. 导入运行时认证材料

从 Mac 菜单栏选择“导入运行时认证材料…”，选择包含以下两个文件的 `authentication` 目录：

```text
authentication/
├── identity.pk8
└── certificate.p7b
```

材料只会复制到这台 Mac 的私有运行时目录，不会上传，也不会覆盖已有身份。不要将这些文件提交到仓库或粘贴到聊天中。

### 3. 配置原生地图坐标策略

iPhone 原生 MapKit 在中国大陆返回的地图坐标需要与 WGS84 报点目标区分。Loc2 默认拒绝未经确认的地图坐标；缺少以下配置时，手机会提示“原生地图坐标尚待本机校准”。手工输入明确的 WGS84 坐标不受此开关影响。

在 `~/.config/loc2/config.json` 中合并 `maps.native`，不要覆盖文件中已有的网络和目标配置：

```json
{
  "nativePhone": {
    "port": 8767
  },
  "maps": {
    "native": {
      "coordinatePolicy": "validated-native",
      "validationEvidence": "tests/test_coordinates.py; docs/native-app-validation-2026-10-31.md"
    }
  }
}
```

`coordinatePolicy` 与非空的 `validationEvidence` 必须同时存在，修改后重新打开 Mac App。本仓库中的引用对应当前原生 MapKit 中国地区坐标路径的实测记录和独立 WGS84 对照；更换地图提供方、坐标实现、目标地区或无法复用该证据时，应重新校准，不能填写占位字符串直接放行。

可以用以下命令检查本机字段是否完整：

```sh
jq -e '.maps.native.coordinatePolicy == "validated-native" and
       ((.maps.native.validationEvidence // "") | length > 0)' \
  ~/.config/loc2/config.json
```

### 4. 扫码授权并绑定目标 iPhone

1. 保持 Mac 与 iPhone 在同一局域网，从 Mac 菜单栏选择“配对手机控制端”。
2. 用 iPhone Loc2 扫码，并在 Mac 上批准请求。首次扫码授权不需要 USB。
3. 在配对窗口的“已授权控制端”中选择该手机，点击“绑定蓝牙目标…”。
4. 在 iPhone 打开“设置 → 蓝牙”并保持页面打开；按 Mac 提示完成系统蓝牙配对。
5. 回到 Loc2，确认选中的是扫码的同一台 iPhone，再点击“确认绑定”。

只完成扫码时，手机可能显示“已配对，待配置报点目标”。绑定成功后授权会自动升级，无需重新扫码。不要手工复制另一台 Mac 的蓝牙目标、TLS 证书或 `grants.json`。

### 5. 初始化无线网络

需要无线报点时，从 Mac 菜单栏依次执行：

1. “初始化或更新网络授权…”
2. “检查当前网络”

Loc2 将当前网络信息保存在本机钥匙串中，并继续使用自动接口选择。更换 Wi-Fi、修改密码或钥匙串授权失效后，需要重新执行这一步。

当前支持已验证的 WPA2，以及具有配套运行时能力的 WPA2/WPA3 混合模式。仅 WPA3 网络尚未通过兼容性验收，应用不会把它伪装成 WPA2；遇到相关提示时应改用已验证的混合模式或 USB。

### 6. 首次验证

首次使用建议选择一个附近且有独立参照的地点，完成一次“应用位置 → 手机观察 → 停止报点 → 确认恢复”的短流程。开始前检查：

- Mac 详情显示运行时与认证材料已就绪，且没有网络错误。
- iPhone 诊断页显示“原生地图校准：已配置”。
- 当前 Mac 在线、报点目标可用，且没有另一台 Mac 的未结束会话。
- 无线模式下网络检查通过；USB 模式下连接的是配置绑定的同一台 iPhone。

## 换电脑与重新安装

同一台 Mac 覆盖安装 `/Applications/Loc2.app` 时，`~/.config/loc2` 和 `~/Library/Application Support/loc2` 不在 App 包内，正常情况下会保留。新 Mac 不会自动拥有旧电脑的本机状态，应按以下规则迁移：

| 项目 | 新 Mac 的处理方式 |
| --- | --- |
| `maps.native` 校准策略 | 确认仍适用于当前 App、地区和坐标实现后，可迁移证据引用 |
| 运行时认证材料 | 从有权使用的原始材料重新导入 |
| TLS 身份与 `grants.json` | 不复制；在新 Mac 重新扫码授权 |
| 蓝牙／USB 目标 | 在新 Mac 重新确认并绑定 |
| Wi-Fi 凭据 | 在新 Mac 重新初始化到本机钥匙串 |
| `interface` / `wifiInterface` | 不迁移；默认由当前 Mac 的路由自动选择 |

建议在迁移前单独记录非敏感的 `maps.native` 配置和校准报告引用。不要把整个私有配置目录提交到 Git，也不要用复制旧 TLS 私钥来跳过新电脑配对。

## 常见提示

| 提示 | 含义与处理 |
| --- | --- |
| “原生地图坐标尚待本机校准” | `maps.native` 缺失或证据为空；按首次设置第 3 步配置并重启 Mac App |
| “已配对，待配置报点目标” | 只完成了控制授权；在 Mac 配对窗口绑定同一台 iPhone 的蓝牙目标 |
| “运行时认证材料不完整” | 从 Mac 菜单栏重新导入包含两个认证文件的目录 |
| “当前 Wi-Fi 尚未初始化” | 执行“初始化或更新网络授权…”后再检查网络 |
| “WPA3 需要已确认的混合模式及配套运行时” | 当前网络不满足已验证条件；使用 WPA2/WPA3 混合模式或 USB |
| 二维码未出现或手机无法连接 Mac | 确认 Mac 有默认路由和私有 IPv4、两端同网、端口 8767 可用；不要硬编码其他电脑的接口名 |

更完整的 Mac 状态、配对和网络说明见[Mac 应用与本机配置](docs/mac-app.md)。

## 使用原则

- 搜索、长按地图、选择收藏或输入坐标只改变草稿。
- 点击“应用位置”才创建报点会话。
- Mac 退出、睡眠、链路失败或主动停止会结束当前会话。
- USB／无线通道变化不会自动重放目标；需要重新明确应用。
- Mac 显示已发送不代表 iPhone 已采用目标，必须观察手机系统位置。
- 停止后继续观察真实位置是否恢复；必要时使用 App 提供的定位服务设置入口。

## 开发

源码构建需要 Xcode Command Line Tools 和 Python 3.9 或更新版本。普通源码构建不包含第三方运行时和认证材料。

```sh
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open 'build/Loc2.app'
```

构建或测试请使用系统／开发环境中的 Python，不要把认证材料、本机配置或诊断日志加入仓库。完整 Release 的构建与校验命令见[应用 Release](docs/releases.md)。

## 相关文档

- [Mac 应用与本机配置](docs/mac-app.md)
- [应用 Release](docs/releases.md)
- [手机配对、持久授权与撤销](docs/phone-control.md)
- [Apple 地图选点与校准策略](docs/apple-map-selection.md)
- [USB 优先双通道架构](docs/adr/0004-usb-preferred-dual-transport.md)
- [多 Mac 配对架构](docs/adr/0005-multiple-paired-computers.md)
- [领域术语](GLOSSARY.md)
