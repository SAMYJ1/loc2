# USB 隐藏画面验证准备

这是 Issue #2 的准备工具，不是已完成的真机验证，也不是完整应用后端。它只生成一个仓库外的运行覆盖目录，不启动 Receiver、不枚举或连接手机、不创建 `ARM_LOCATION`。

## 准备

```sh
python3 tools/usb_validation/prepare.py --resources /absolute/path/to/macplay-mvp/resources --output /absolute/path/to/new-private-run
```

输出目录必须是全新目录，且位于本仓库及原资源目录之外。目录权限为 0700。工具写入两个修改后的 engine 文件、白名单顶层 JavaScript 与 protocol JavaScript 副本、可审阅的 `hidden-video.patch` 和包含前后 SHA-256 的 `preparation.json`；二进制、媒体库和 node_modules 通过白名单符号链接复用。原目录不修改。认证资料、设置及配对记录不复制，protocol 中的非 JavaScript 文件也不会被带入。

该目录包含本机依赖链接，不能作为可分发包、提交到 Git 或整体上传。新数据目录最初为空。

## 修改与运行契约

- 将媒体模块的首次帧显示、显式显示两处调用从 `macplayWindowHandle` 换为 `macplayPrepareVideoWindow`。
- 保留同一个 native contentView 的创建、视频解码、帧统计、健康监测、恢复和销毁。
- engine JavaScript 保持在同一份实际目录中。不能把 protocol 或顶层 JavaScript 软链接回原 engine：Node 会按真实路径解析相对依赖，导致协议层和主循环加载两份 media 模块，接收状态与就绪回调分离。
- 修正主模块的 `showCarPlay` 信号及日志，避免隐藏模式仍声称窗口已显示。
- 检查所有预期替换的数量。上游形状变化即拒绝准备，重新阅读上游后调整工具。
- Receiver 启动接口仍是 `resources/runtime/MacPlayReceiver.app/Contents/MacOS/MacPlayReceiver resources/engine/main.js`，环境变量沿用原实验控制器。
- 原实验控制器可通过 `--workspace <输出目录>` 使用该覆盖目录。其限时、真实订阅、手动 arming 和 STOP 机制不变；它不是最终应用的无限持续策略。

真正运行前，执行端必须在私有 `data` 目录准备此前获授权的 authentication 和配对 identity，确认指定 USB 手机、WGS84 测试点和时长。不要从仓库寻找或生成认证身份。不要将 identity 根目录直接链接为共享 data，否则 settings 和运行状态可能写回原实验。凭据的具体安全准备由现场运行步骤完成，本工具不会代做。

准备命令结束不是启动命令，也不表示会话健康。后续实际启动仍由应用适配器或原控制器显式执行。

## 已检查的 native 路径

本机原实现中 `macplay_prepare_window` 调用 `mpWindow(aspect, false)`。窗口内容 view 创建完成后，`if (!present)` 立即返回 contentView；激活应用、`makeKeyAndOrderFront` 和 `orderFrontRegardless` 位于其后。`applicationDidBecomeActive` 对不可见窗口直接返回。媒体模块用 prepare 返回的同类 handle 创建解码器。

上述为源码检查，尚未证明隐藏 view 在真实视频流下持续解码。对应二进制能力、画面是否始终隐藏、帧数持续增加和手机位置采用须最终真机验收。

## 离线验证

```sh
python3 -m unittest discover -s tests -p test_usb_prepare.py
node --check /absolute/path/to/new-private-run/resources/engine/media.js
node --check /absolute/path/to/new-private-run/resources/engine/main.js
```

CLI 测试通过临时假资源检查准备行为、原文件不变、认证/未知文件不进入输出，以及上游不匹配时拒绝生成。Node 模块图回归从协议目录和顶层依赖触发事件，验证两者能到达准备目录的同一个 media 回调。它们不模拟手机采用，也不加载真实 native addon。

2026-10-29：3 个 CLI 测试通过；实际本机资源 prepare 成功；两个生成 JS 通过语法检查。没有启动 Receiver 或 USB 报点。

本轮资源指纹：

| 文件 | 原始 SHA-256 | 隐藏版 SHA-256 |
| --- | --- | --- |
| media.js | 5d897b6f5e117f1efae43dac4ea94a220136dea2c5c54df434db92d09e274f60 | 25d54868b42fa2fc9dc16b547e7f9cde9185df85545c506b8b2d4613d1a088e6 |
| main.js | de89da3e24b53c863c82eb0a4c75484cb1c948c1f369b74bfff6d1c54bde7b87 | 9bfa940d05b4b612d440fcb76a0ceb984cf280b3c9d832d1522575052cb9f154 |

2026-10-30：修复了相对模块经过符号链接回到原 engine 的问题，新增 CLI/Node 回归（修改前失败、修改后通过）。4 项准备工具测试和全量 43 项 Python 测试通过。修复后的无坐标诊断约 3.5 秒得到首帧与隐藏就绪信号；随后应用附近点隐藏模式的采用、无投屏窗口及恢复均获用户确认，见[隐藏模式验收](../../docs/hidden-mode-validation-2026-10-30.md)。旧准备目录不会被原地更新，需重新生成并明确切换本机配置。

## 最终真机验收记录

执行前明确运行时长、采用判定容差和观察方式，随后逐项记录：

1. 当前设备及系统、实际真实位置基线、测试目标及观察应用。
2. authentication、真实 Start/Stop、首次解码与后续帧数；整个过程无可见 CarPlay 窗口。
3. 本地接受/入队与手机位置采用分别记录；不以计数推导采用。
4. 停止时间、进程退出及停止报点确认。
5. 手机恢复真实位置的独立观察和时间，必要的手动刷新动作。

依用户调整，真机检查汇入最终验收；本工具交付不把这些项目标记为已通过。
