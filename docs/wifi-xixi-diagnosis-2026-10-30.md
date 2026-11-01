# 西溪天街无线复测：首次插件扫描阻塞诊断

日期：2026-10-30。针对 [37.6秒提前退出的复测](wifi-xixi-retest-2026-10-30.md)继续排查。此前 [成功轮](wifi-xixi-validation-steps-2026-10-30.md)保持为独立历史记录。

## 定位到的故障

新复制运行时第一次处理视频配置时，在 Node 主线程同步调用 `addon.createPlayer()`。它进入 `Player::new_with_decoder → ensure_init → gst_init_check → gst_update_registry`，等待插件扫描器。主线程采样记录到 `plugin_loader_free → exchange_packets → gst_poll_wait`。同步阻塞期间，JS 事件循环不能及时处理 CarPlay 控制消息，手机连接随后断开，解码帧数为零。

在全新副本上实测：窗口准备262毫秒，`createPlayer()`耗时25857毫秒，事件循环停顿26207毫秒。控制通道关闭是后续结果；仅看该错误容易把排查方向放在网络或位置订阅上。

首次扫描为什么耗时约20至26秒尚未继续拆分到扫描器内部或系统加载层；现有证据不支持归因于 VPN、开发者模式、目标距离或手机不支持无线位置。

## 准备过程的差异

原成功轮新建会话目录，但 `resources` 指向已固定的 `usb-restore-232231/resources`。失败复测则把整套运行时复制到新路径，改变了首次加载条件。helper、接收端、JS 内容相同，身份、证书和配对文件也相同，但内容哈希一致不等于运行时初始化状态一致。

## 单变量诊断

所有下列诊断均不创建 `ARM_LOCATION`，位置发送为零：

| 场景 | 结果 |
|---|---|
| 重用已经启动过的失败副本 | 5.611秒通过首帧解码 |
| 全新副本，记录关键调用计时 | `createPlayer()`阻塞25.857秒；收到57帧、解码0帧；39.729秒退出 |
| 全新副本，先初始化再建连 | 插件初始化21.541秒；会话内 `createPlayer()`仅24毫秒；首帧解码通过 |

这组对照将首帧失败复现到新副本的首次插件扫描路径。没有用绕过首帧判据或放宽报点条件来掩盖失败。

## 独立运行时修正

仅在独立运行时的 `engine/main.js` 增加启动前初始化。在网络配置检查通过之后、启动 helper 和控制服务之前执行：

```javascript
// Prime plugin discovery before accessory/control sessions open.
diagnostic('media-preflight-start');
const mediaPreflightStarted = Date.now();
media_1.addon.probeCodecs();
diagnostic('media-preflight-ready', {
  durationMs: Date.now() - mediaPreflightStarted,
});
```

这把可能较慢的插件发现移到建连前。同一进程后续创建播放器不再执行首次扫描。120秒报点窗口仍从首次实际发送起算，总运行上限仍为360秒。

原始成功运行时和 helper 均未改动。修正副本 helper SHA-256 仍为 `40f89f1bfbb183c028a169f7a40a89f88c3a0300d9cc5b0c53ea3202af7f58f5`。最终副本中已移除所有临时计时探针，只有上述启动预热和对应状态日志。

## 完整定位复测

最终使用另一个全新副本，不带临时计时探针。前置查询确认 iOS 27.0 / 24A435、开发者模式 enabled、USB 为零、网络元数据与成功轮一致。用户确认 VPN、蓝牙和同网条件保持不变，起始蓝点为真实位置。

本轮预热20413毫秒；认证、首帧解码通过后才放行报点。用户确认未开关定位服务，Apple 地图和高德均稳定在西溪天街。

| 验证项 | 最终结果 |
|---|---|
| 报点窗口 | 完整120秒，全程153.029秒（包含启动及预热） |
| 本地接受／位置消息入队 | 118组／236条 |
| 视频 | 末次统计收到1011帧、解码1011帧 |
| 位置采用 | 用户确认两个 App 均稳定在西溪天街，未刷新定位服务 |
| 真实位置恢复 | 用户确认停止后未刷新定位服务，两个 App 均恢复真实位置 |
| 退出原因 | test-duration-complete |
| 清理 | 接收端、helper、蓝牙桥、插件扫描器均无残留 |
| 结束条件 | USB仍为零、网络地址未变化、开发者模式直接查询仍为 enabled |

本轮新建的网络配置和设置文件中的密码副本已清空。原始成功版本未覆盖；本次改动仅在独立实验运行时，不代表 Location Lab 应用已集成无线模式。

### 后续复现入口

已修正运行时在本机 `work/xf-n5x7amtt/resources`，补丁为同目录上一级的 `prewarm.patch`。下一轮仍应新建会话目录，单独准备 data、网络配置和控制标记，并引用该已修正运行时。不要复用已经完成测试的工作目录直接启动，那里保留了旧控制标记与 socket 路径。

启动时先确认日志顺序为 `media-preflight-start → media-preflight-ready → starting`，再按原文档等待认证和视频首帧，通过后才创建新会话目录中的 `ARM_LOCATION`。`STOP` 可要求控制器结束本轮会话；停止后仍应独立确认真实位置恢复。

诊断脚本 `work/wireless-diagnostics/probe.py --resources <固定运行时/resources>` 只验证认证和首帧解码，从不创建 ARM_LOCATION；首帧通过返回0，超时或提前退出返回1。本次已实跑未修正新副本失败和预热新副本通过两种结果。

## 本机证据

- 首次失败：`work/xr-67w0gpov`。
- 已使用副本重连：`work/xd-l2w7e20z`。
- 新副本复现及主线程采样：`work/xd-2z4xjz69`。
- 提前初始化对照：`work/xd-wwlzmsb3`。
- 最终修正及完整验证：`work/xf-n5x7amtt`，包含可审阅的 `prewarm.patch`。
- 诊断脚本及脱敏时序：`work/wireless-diagnostics`。

以上路径相对本机调研目录 `/Users/eugene/Documents/Codex/2026-10-15/bang-w`，不包含在本仓库。诊断用的额外运行时副本已移除，日志和采样仍保留本机。认证材料、设备标识、配对记录及原始日志不复制进仓库。
