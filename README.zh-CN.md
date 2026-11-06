# Loc2

[English](README.md) · **简体中文** · [下载安装包](https://github.com/SAMYJ1/loc2/releases)

在 iPhone 上选择目标位置，由 Mac 通过 USB 或无线连接向手机提供该位置。Loc2 是一个用于个人定位测试的工具，包含 iPhone 原生 App 和 Mac 菜单栏 App。

- **iPhone**：搜索 Apple 地图、选点、输入 WGS84 坐标，管理收藏和最近使用地点。
- **Mac**：维持已授权连接，向绑定的 iPhone 持续提供位置数据。
- **用户**：明确点击应用，并在手机上确认位置是否实际采用。

Loc2 需要一台 Mac，以及单独准备的配件认证材料。它属于实验性工具：iOS 可能拒绝或筛选外部位置，发送成功不代表手机已经采用目标位置。

## 主要功能

- 地图搜索、长按选点、手工坐标、收藏和最近使用目标。
- USB 与无线报点；配置双通道后优先使用 USB。
- 二维码授权、TLS 连接和明确的目标手机绑定。
- 同一台 iPhone 保存多台 Mac，自动寻找可用电脑。
- 在 App 内登录 GitHub，从指定私有仓库下载认证材料。
- 明确的应用与停止操作；重连或切换电脑不会自动重放旧目标。

收藏、最近使用地点和选点草稿保存在 iPhone 上。活动定位会话由 Mac 管理，报点期间需要保持 Mac App 运行。

## 使用要求

| 项目 | 要求 |
| --- | --- |
| Mac 安装包 | Apple Silicon，macOS 26.0 或更新版本 |
| iPhone App | iOS 17.0 或更新版本；开发签名安装需开启 Developer Mode |
| 首次扫码 | Mac 与 iPhone 在同一局域网，Mac 有可用的私有 IPv4 地址 |
| 无线使用 | 完成系统蓝牙配对，Loc2 可读取 Wi-Fi 凭据；使用 WPA2 或受支持的 WPA2/WPA3 混合网络 |
| 认证材料 | 有权使用的 `identity.pk8` 和 `certificate.p7b`，需要单独导入 |

完整 Mac 安装包已内置运行时、Python 和 GitHub CLI，不包含认证材料。GitHub 自动导入要求账号已有私有仓库访问权限，登录本身不会授予该权限。

Mac 包使用开发签名，尚未公证。提供的 IPA 同样为开发签名，只能安装到描述文件覆盖的设备，并受签名有效期限制；具体信息见 Release 说明。其他 iPhone 需要使用自己的开发团队构建并签名。

## 安装

仓库为私有时，下载安装包需要相应的 GitHub 访问权限。

1. 从 [Releases](https://github.com/SAMYJ1/loc2/releases) 下载 Mac ZIP 和适用的 iOS 安装包，核对 `SHA256SUMS` 与 `release-metadata.json`。
2. 解压 ZIP，将 `Loc2.app` 放入 `/Applications`，然后打开。
3. 使用 Xcode 或 Apple Configurator 将 IPA 安装到符合签名条件的 iPhone，或安装自己签名的版本。

完整 Mac 包会自动准备本机运行时目录，无需另外安装 Python 或填写 `runtime` 路径。安装或打开 App 不会开始报点。

## 首次设置

每台 Mac 都需要独立完成以下设置。

### 1. 导入认证材料

在 Mac 菜单或详情窗口选择 **“从 GitHub 登录并导入认证材料…”**，使用有 `SAMYJ1/loc2-private-auth` 访问权限的账号登录。浏览器授权页显示的应用名称是 **GitHub CLI**。授权后，Loc2 从同一仓库提交中下载两份文件，核对 SHA-256 摘要，再导入本机。

已有文件时，也可选择 **“导入运行时认证材料…”**，选中以下目录：

```text
authentication/
├── identity.pk8
└── certificate.p7b
```

没有私有仓库权限时，需要自行准备有权使用的材料。已有不同身份不会被覆盖。请勿将这些文件放入应用源码、公开 Release 或日志。

### 2. 扫码授权并绑定蓝牙目标

以下为无线首次设置，安装 App 后请先拔掉 iPhone 与 Mac 之间的 USB 线。

1. 保持两端同一局域网，从 Mac 菜单选择 **“配对手机控制端”**。
2. 在 iPhone App 点击 **“扫码连接”**，扫描二维码。添加另一台 Mac 时，可在 App 设置中选择 **“添加电脑：扫描二维码”**。随后在 Mac 批准请求。
3. 在 Mac 配对窗口的 **“已授权控制端”** 中选择这台手机，点击 **“绑定蓝牙目标…”**。
4. 在 iPhone 打开 **“设置 → 蓝牙”** 并保持页面打开。点击 Mac 的 **“搜索并配对附近手机…”**，在系统蓝牙设置中完成配对。已经配对的手机可直接从列表选择。
5. 返回 Loc2，确认所选设备是扫码的同一台 iPhone，再点击 **“确认绑定”**。

扫码授权无需 USB。蓝牙绑定会自动读取设备地址并更新已有授权，无需再次扫码。此流程配置的是无线模式；USB 优先使用需要另外完成双通道配置，详见 [Mac 设置指南](docs/mac-app.md)。

### 3. 准备无线网络

从 Mac 菜单依次执行 **“初始化或更新网络授权…”** 和 **“检查当前网络”**，按 macOS 提示允许识别当前 Wi-Fi 和访问其凭据。

Loc2 会自动选择局域网接口。Wi-Fi 凭据变化或钥匙串访问失效后，需要重新授权。当前运行时不支持纯 WPA3 网络；WPA2/WPA3 混合模式也需要通过兼容性检查。

### 4. 选择目标位置

首次检查可在 iPhone 点击 **“输入坐标”**，输入已知为 **WGS84** 的纬度、经度。使用 Apple 地图搜索或长按选点时，还需要完成下方的地图坐标策略配置。

应用前确认 Mac 在线、目标可用，并且 Mac 详情窗口没有认证材料或网络错误。

## 日常使用

1. 保持 Mac App 运行，在 iPhone 打开 Loc2。
2. 搜索、地图选点、输入坐标或选择收藏。此时只准备草稿。
3. 点击 **“应用位置”**，然后在手机上核对实际位置；仅看 Mac 发送计数不能确认位置采用。
4. 使用结束后，在 iPhone 点击 **“恢复”**，或在 Mac 点击 **“停止报点”**。观察手机是否返回真实位置，再确认恢复；必要时按照 App 的定位设置引导，手动关闭再开启定位服务。

关闭 iPhone App 不会停止 Mac 上的活动会话。退出或休眠 Mac、报点通道断开、主动停止都会结束会话；重连或切换通道后需要重新点击应用。切换电脑前，应先处理原电脑上可能仍在运行的会话。

## 启用 Apple 地图选点

手工输入 WGS84 坐标不需要此设置。要应用 Apple 地图搜索或长按选中的地点，Mac 必须配置经过验证的原生地图坐标策略，尤其需要区分中国大陆的地图坐标与实际报点使用的 WGS84 坐标。

确认验证依据适用于当前 App 和目标地区后，将以下内容合并到 `~/.config/loc2/config.json`，保留已有配置：

```json
{
  "maps": {
    "native": {
      "coordinatePolicy": "validated-native",
      "validationEvidence": "tests/test_coordinates.py; docs/native-app-validation-2026-10-31.md"
    }
  }
}
```

重新打开 Mac App，iPhone 诊断页应显示 **“原生地图校准：已配置”**。两个字段缺一不可。示例引用的是本项目的坐标验证记录，填写配置不会自动执行校准；地图提供方、坐标实现或目标地区不同时，应重新验证并填写对应证据，不使用占位字符串直接放行。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 没有二维码或无法连接 Mac | 确认两端同网、Mac 有私有 IPv4、默认端口 `8767` 可达；不要复制另一台 Mac 的接口名 |
| 已配对但目标不可用 | 在 Mac 完成蓝牙目标绑定；扫码只建立控制授权，还需明确报点目标 |
| GitHub 下载失败 | 登录账号必须有指定私有仓库的读取权限；必要时使用窗口里的账号切换按钮 |
| 缺少认证材料或后端启动失败 | 导入两份认证文件，并查看 Mac 详情中的运行时状态 |
| 原生地图坐标尚待校准 | 按上方说明配置经过验证的策略，或先输入 WGS84 坐标 |
| WPA3 兼容性提示 | 使用受支持的 WPA2 或 WPA2/WPA3 混合网络及配套运行时，或已配置的 USB 通道 |
| 停止后仍显示目标位置 | 在手机上单独检查恢复；未恢复时按定位设置引导处理 |

## 数据与多台 Mac

地点和已配对电脑记录保存在 iPhone 本机。Mac 配置及授权保存在 `~/.config/loc2`，私有运行时数据保存在 `~/Library/Application Support/loc2`。

覆盖安装 Mac App 通常会保留这些目录。新 Mac 需要重新导入认证材料、扫码授权、绑定目标并初始化网络；各电脑的 TLS 身份、授权和网络配置应独立保存。坐标验证引用只有在仍然适用时才能复用。

## 从源码构建

Mac App 和 Python 测试需要 Xcode Command Line Tools 与 Python 3.9+。iOS 构建需要完整 Xcode；真机版本还需要自己的 Apple 开发团队和签名配置。

```sh
git clone https://github.com/SAMYJ1/loc2.git
cd loc2
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open build/Loc2.app
```

```sh
# iOS 模拟器版本
sh scripts/build-ios-app.sh simulator

# iPhone 真机签名版本：将 YOUR_TEAM_ID 替换为自己的开发团队 ID
LOC2_TEAM=YOUR_TEAM_ID sh scripts/build-ios-app.sh device
```

普通源码构建不会打包第三方运行时、Python 或 GitHub CLI。可按 [Mac 指南](docs/mac-app.md) 配置本机运行时，或按 [Release 打包说明](docs/releases.md) 生成完整安装包。认证材料始终需要单独提供。

## 更多文档

- [Mac 配置、配对、网络和 USB 通道](docs/mac-app.md)
- [Release 打包与签名](docs/releases.md)
- [配对与授权](docs/phone-control.md)
- [领域术语](GLOSSARY.md)
