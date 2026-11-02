# 应用 Release

GitHub Releases 用于分发应用产物，源码仓库不保存运行时二进制或私密材料。当前仓库保持私有；下载需要仓库访问权限。

## 使用安装包

- **macOS ZIP**：解压后将 `Loc2.app` 放入应用程序目录。包内包含定位运行时与 Python；首次运行自动建立本机私有数据目录，不需要手写 `runtime` 路径。有效的既有运行时配置继续沿用。
- **iOS IPA**：当前为开发签名，仅供描述文件中登记的设备安装，设备需要 Developer Mode。用 Xcode 或 Apple Configurator 安装；在 GitHub 下载 IPA 不等于可以直接在任意 iPhone 上安装。签名到期后需要重新构建／签名。
- **本机认证材料**：安装包不包含 `identity.pk8`、`certificate.p7b`、旧电脑的配对身份、扫码授权或 Wi-Fi 凭据。首次使用在 Mac 菜单选择“导入运行时认证材料…”，选择自己有权使用的认证目录。材料仅复制到本机私有目录；不覆盖已有身份。配件配对身份由引擎在首次明确应用时在这台 Mac 单独生成。
- 当前可用运行时是 **Apple Silicon / macOS 26.0 或更新版本**。最低系统版本来自实际依赖，其中 `libgstapplemedia.dylib` 要求 26.0；不能仅修改 App 的最低版本声明来支持旧系统。
- 当前 Mac 包使用开发签名，**尚未 notarize**。这是个人开发预览版，不是已完成 Developer ID 公证的通用发行版。

App 启动和扫码不会报点。首次启动可先完成扫码授权、蓝牙目标绑定；导入认证材料并准备网络授权后，仍需明确点击“应用位置”。完整新 Mac 的真实定位与恢复仍需现场验证。

## 构建发布产物

需要 Xcode、本机可用签名、匹配的运行时资源目录，以及与 `docs/native-runtime-manifest-2026-11-02.json` 匹配的 MacPlay 源码基线。工具不会改写输入运行时或认证目录。

```sh
sh scripts/build-mac-app.sh
LOC2_VERSION=0.1.0 LOC2_BUILD=2026110201 sh scripts/build-ios-app.sh release
python3 scripts/package-release.py \
  --version 0.1.0 --build 2026110201 \
  --runtime-resources /absolute/path/to/runtime/resources \
  --third-party-source /absolute/path/to/macplay/source \
  --ios-app build/ios-device/Build/Products/Release-iphoneos/Loc2.app \
  --output dist/0.1.0
python3 scripts/verify-release.py dist/0.1.0
```

重复打包可增加 `--python-archive /path/to/cached-python.tar.gz` 使用本地下载缓存；仍必须通过固定 SHA-256 校验，不能替换成任意 Python 包。

iOS 构建需要事先在环境中设置 `LOC2_TEAM`；不将签名私钥或本机安装配置提交仓库。版本号和 build 必须与 IPA 内的声明一致。

打包工具执行以下步骤：

1. 验证输入资源完整性和 WPA3 helper 摘要；拒绝私钥、认证文件、本机身份以及资源外部链接。
2. 复制公开运行时程序，修正 Mach-O 动态库开发机绝对路径，重新签名，并核对可携带的依赖路径。保留原 helper 摘要，生成与重新签名后二进制匹配的能力声明。
3. 按 `release/python-runtime.json` 固定版本和 SHA-256 下载 Python Build Standalone，随 App 一起打包。
4. 加入第三方许可声明；另行提供对应 MacPlay/LIVI 源码基线、已应用的 WPA3 补丁和实际 JavaScript overlay，排除认证资产及本机数据。
5. 将签名 iOS App 放入 `Payload/Loc2.app` 导出 IPA；不移除或绕过签名／设备限制。
6. 生成 `release-metadata.json` 与 `SHA256SUMS`。元数据记录源提交、架构、最低系统版本、签名期限和设备数量，不输出设备标识。

验证脚本解压到另一随机路径，检查摘要和代码签名，再用包内 Python 在隔离 HOME、替代硬件发现和回环网络中验证首次扫码与“缺少认证材料”状态。它不连接真实手机，不供给位置。

## 发布

先完成测试并提交构建代码，再以该提交构建产物；发布前核对元数据中的 `sourceRevision`。建议以 `v0.1.0-preview.1` 这样的 prerelease 标签开始。上传 Mac ZIP、开发 IPA、运行时源码包、元数据与校验和；不要上传 `data/`、配置目录或构建日志。

Python 来源与许可：[Python Build Standalone](https://github.com/astral-sh/python-build-standalone)。iOS 开发分发方式：[Apple 的设备分发说明](https://help.apple.com/xcode/mac/current/en.lproj/dev7ccaf4d3c.html)。
