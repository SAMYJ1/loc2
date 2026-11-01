# 外部位置间歇采用：社区与官方证据调查

调查日期：2026-10-30。只读核对公开源码、GitHub Issues/PR/发行说明和 Apple 官方资料；未运行新的手机实验、报点、安装、设置修改或外部发帖。本文采用仓库的“报点／位置采用／恢复真实位置”术语。

## 结论

**社区有相近现象，也有手机日志证实“收到外部位置数据”和“采用该位置”之间存在区别；但没有找到与本机 iOS 27.0（24A435）、USB、相同二进制与身份、开发者模式开启后时好时坏完全对应的公开复现。当前不能宣布唯一根因。**

最有解释力的三条证据是：

1. LIVI 有较接近本案的 **iOS 18.7.2 USB** 一手报告；其位置来源选择和状态变化线索不能直接推广到本机。[LIVI #354](https://github.com/f-io/LIVI/issues/354)
2. DiPlay 有 **iOS 27.0.1 无线**端点拒绝的手机日志；其修复明确 **USB 路径不变**，只能作为分层诊断的参考。[DiPlay #157](https://github.com/shihabal3amri/DiPlay/pull/157)
3. 独立的 USB accessory-location 项目明确记录“链路 ACK 已有、地图不移动”的排障情形，并区分认证、订阅、ACK、地图采用；但它没有公开完整机型/iOS/build 验证矩阵，也不读回 CLLocation 来源，证据弱于带手机日志的案例。[Accessory Location README](https://github.com/aur3l14no/accessory-location/blob/8a13296a3d81dae18ad4481e7a9eca913c2c644f/README.md)

Apple 公开说明是车载 GNSS 与 iPhone 自身传感器共同用于定位，并未承诺已认证配件一定覆盖内部位置；未找到公开文档规定 iOS 27 的精确选择阈值、拒绝条件、状态保留时间，或要求外部 CarPlay 定位必须开启 Developer Mode。[WWDC16：Developing CarPlay Systems, Part 1](https://developer.apple.com/videos/play/wwdc2016/722/)

## 本机已经确认的边界

来源：[10 月 29 日真机记录](../device-validation-2026-10-29.md)、[10 月 30 日旧控制器记录](../device-validation-2026-10-30.md)、[应用验收记录](../app-validation-2026-10-30.md)。

- 同一 iOS 27.0（24A435），旧控制器在 Developer Mode enabled 下曾由用户观察到 Apple 地图采用测试点，并在停止、拔线和刷新后恢复真实位置。
- 后来两轮使用与成功轮次相同的旧控制器、helper/main.js/media.js SHA-256、认证及配对身份，前后均核实 enabled，认证、视频、USB GGA/RMC 入队仍正常，地图仍显示真实位置。
- disabled 下既有历史成功也有后来失败；历史成功紧接 enabled 成功之后。开启 Developer Mode 伴随重启，现场状态并非只改变一个布尔开关。
- 用户补充本次目标与真实位置相距约“几十到几百公里”。不需要保存真实坐标；该距离使外部 fix 与其他来源明显不一致成为值得优先区分的变量，但没有证据给出拒绝阈值或证明存在特定防作弊机制。
- 当前有本地接受/入队和用户地图观察，没有手机原生 CLLocation 时间戳、精度、sourceInformation，也没有逐句手机 NMEA 接收/拒绝记录。
- 因而“当前 helper 永久失效”“只要 enabled 就能成功”“只需恢复旧身份”“新应用独有回归”均不符合现有全部证据。也不能由此排除间歇传输问题或系统采用条件。

本机可见源码另确认：[location 命令处理](/Users/eugene/Documents/Codex/2026-10-15/bang-w/work/macplay-mvp/source/native/livi-helperd/crates/livi-runtime/src/livi_sock.rs:276) 已调用 `push_location`，并非 LIVI #354 原来固定返回成功的空实现；[位置发送函数](/Users/eugene/Documents/Codex/2026-10-15/bang-w/work/macplay-mvp/source/native/livi-helperd/crates/livi-runtime/src/bringup.rs:631) 在 `ch.send` 返回后记 `location-message-queued`，而 [LinkChannel.send](/Users/eugene/Documents/Codex/2026-10-15/bang-w/work/macplay-mvp/source/native/livi-helperd/crates/livi-runtime/src/driver.rs:20) 仅将帧交给本地 `out_tx`。因此现有 queued 计数止于本地通道队列，不能证明手机 ACK、解析或采用。这是本机源码核查，不是对远端 upstream 当前版本的断言。

本轮还只读比较了保存的成功与失败原始记录：

| 同为 enabled 的老控制器轮次 | 接受 / 入队 | 刷新相关时间线 | 手机观察 |
| --- | --- | --- | --- |
| 成功轮次 | 101 / 202 | 约 73 秒恢复订阅后，有约 33 秒持续供数，随后还有一次重订阅 | 用户确认到测试点并最终恢复 |
| 后续失败 1 | 109 / 218 | 约 110 秒恢复稳定订阅，结束前只剩约 14 秒 | 仍是真实位置 |
| 后续失败 2 | 119 / 238 | 窗口内没有捕获额外 Stop/Start，无法凭日志确定刷新时间 | 用户报告刷新后仍是真实位置 |

三轮均未记录 `location-send-failed` 或 link pump 结束错误，但这不能补足手机接收证据。失败轮次的本地计数甚至高于成功轮次，因此“多发几包就能证明正常”不成立。观察窗口不一致也使现有轮次无法直接区分设备状态、数据采用和人工操作时序。

## 一手来源及与本案的关系

### 1. LIVI #354：USB 接收与采用的区别

2026-09-21，macOS 14.6.1、iOS 18.7.2、USB。作者发现 helper 只回复成功而未发送；维护者随后确认补入。修复后，手机日志显示收到 NMEA，但自身定位良好时仍保留自身位置。作者还报告跨洲点短暂生效后失效，组合调整其他定位来源及重启后，附近约 800 米的点可用。[原帖](https://github.com/f-io/LIVI/issues/354)、[维护者回复](https://github.com/f-io/LIVI/issues/354#issuecomment-5769678182)

这是带手机日志的一手案例，但“位置不可信”的因果解释属于作者推测；多个条件同时变化，不能给出距离阈值或 iOS 27 规则。本机已具备非空发送路径，不能照搬其原始 no-op 缺陷。

### 2. DiPlay #157：发送后仍被手机端拒绝

2026-10-03 合并，0.2.11，iPhone 17 Pro Max/iOS 27.0.1，无线。作者的 `accessoryd` 日志显示蓝牙先占位置端点，Wi-Fi 的 633 条位置消息被拒。改为由 Wi-Fi 独立声明并等待订阅后，7 分钟复测的 5 次位置 Start 均接受；仅一包在 Stop 后到达而被拒。PR 明确 USB 路径未改。[PR #157](https://github.com/shihabal3amri/DiPlay/pull/157)

它强力支持分层诊断，但不直接解释本案 USB。接收处理成功也不等于每个坐标都成为最终 CLLocation；测试构建含其他改动，不能扩大为整个发行版已验收。

### 3. DiPlay #48：场景切换、旧 fix 和订阅跨链路曾导致间歇供数

**日期／版本：** 2026-09-29 创建、09-30 合并，基于 0.2.7；BYD Tang、DiLink 5.0/Android 12，iPhone 15 Pro、作者仅写 iOS 27，未给完整 build。主要为无线，另有 USB 日志。

**作者直接记录：** 无线认证后约 2 秒转到 Wi-Fi，原位置请求留在蓝牙；倒车摄像头等其他 Android 应用遮挡 CarPlay 超过 30 秒时，接收端定位更新被 Android 停止，最后 fix 超过有效期后 GGA/RMC 消失；USB 曾在 130ms 里发 11 包，并有手机 Stop 后仍到达的排队消息被拒。PR 修正接收端前台服务和发送节流。[PR #48](https://github.com/shihabal3amri/DiPlay/pull/48)

**关键更正：** #48 把蓝牙订阅延续到 Wi-Fi 的早期做法，后来被 #157 的手机日志证明存在端点归属问题并移除。#48 自己也明确未验证 iOS 最终采用车机位置。不能只阅读较早的“修好了”标题就推断系统采用成功。

**与本案关系：** 支持检查事件所属会话、Stop/Start、排队包、发送间隔和时间戳；Android 前台服务被限流不适用于 macOS，本机已有持续 1 Hz 报点也降低了“完全同类供数停止”的解释力。

### 4. Accessory Location：独立 USB 实现承认 ACK 后仍可能不采用

**日期／版本：** 本次读取的 README 最近修改提交为 2026-10-15 的 `8a13296a3d81dae18ad4481e7a9eca913c2c644f`。未找到公开的精确手机/iOS/build 成功矩阵；本次 GitHub issue 搜索没有返回用户问题。

该项目通过 `com.apple.carkit.service`、认证、真实位置请求发送 GGA/RMC，文档将 link acknowledgement 与 adoption 分开；排障表包含“收到 ACK、位置未移动”，建议定位服务重新开关，但同时承认 iOS 仍可拒绝 fix。作者也写明工具不能读回手机坐标或来源字段。协议说明发送时生成 UTC、尊重订阅间隔，单包等待 ACK、有重传，Stop 立即清订阅。[README](https://github.com/aur3l14no/accessory-location/blob/8a13296a3d81dae18ad4481e7a9eca913c2c644f/README.md)、[协议文档](https://github.com/aur3l14no/accessory-location/blob/8a13296a3d81dae18ad4481e7a9eca913c2c644f/docs/protocol.md)

**证据强度：作者实现和排障说明，低于完整实测日志。** 它证明社区实现认识到此边界，不证明相同 iOS 27.0 条件下一定靠刷新解决。本文未安装或运行该项目；其 README 中的命令仅作为来源，不是当前执行建议。

### 5. CPC200-CCPA 逆向记录：手机收到 NMEA 后仍需进入融合

**日期／版本：** 作者将端到端段落标作 2026 年 2 月实测，固件 `2025.10.15.1127`；文件最近修改提交为 2026-07-08 的 `cf363d3522f6f327ac99cb57029a9257f8f35149`。原文写 GM AAOS 模拟器＋CPC200-CCPA＋“iPhone Air (iOS 18)”，没有完整系统/build，设备描述未交叉核实，需降低权重。

作者列出 `accessoryd → locationd` 的 NMEA 通知以及 `CL-fusion` 日志，然后把观察概括为按最佳精度选择。**日志摘录是作者一手观察；“best-accuracy-wins”是该作者的模型归纳，不是 Apple 公开保证，也不足以证明只有 horizontalAccuracy 一个变量。** [固定版本协议记录](https://github.com/lvalen91/CPC200-CCPA_resources/blob/cf363d3522f6f327ac99cb57029a9257f8f35149/documentation/02_Protocol_Reference/usb_protocol.md)

它与本案相通之处在于分出“发送／手机解析／融合”；但硬件盒子和固件管线不同。该文关于 timestamp=0 的具体问题属于 **Android Auto 路径**，不可套到本机 iAP2 GGA/RMC。

### 6. 更近版本的“没用车机 GPS”报告，有些并未证明不采用

| 来源 | 日期与环境 | 原帖及后续 | 证据判断 |
| --- | --- | --- | --- |
| [DiPlay #979](https://github.com/shihabal3amri/DiPlay/issues/979) | 2026-10-19；0.2.21，iOS 27.0.1，BYD 唐 DiLink 4.0，无线车机热点 | 用户关闭百度地图定位权限后无法定位，据此认为未用车机 GPS；评论者指出应用失去系统位置权限后所有来源都不可用，用户接受并撤回原归因，维护者 10-21 关闭 | 有相似疑问，**不是有效的不采用证明**。评论所列每分钟 60 次发送同样不是手机采用证据 |
| [DiPlay #1174](https://github.com/shihabal3amri/DiPlay/issues/1174) | 2026-10-28；0.2.21，iOS 27.2，元 Plus，DiLink 3.0/Android 10，USB 和无线 | 用户以旋转手机时地图箭头随动，判断位置来自手机；只有另一车主附议 | 朝向和经纬度是不同观测，未附原生来源字段，不能证明 GGA/RMC 没被采用 |
| [DiPlay #1179](https://github.com/shihabal3amri/DiPlay/issues/1179) | 2026-10-29；五菱星光 730/Android 13，未写具体 iPhone/iOS/DiPlay 版本 | 请求用车机 GPS 替代手机，称车内信号差、耗电；尚无评论或位置来源日志 | 需求和自述，弱证据；不是与本案同版本的复现 |

### 7. MacPlay 与 PlayPort 检索结果

2026-10-30 检查两仓库所有可检索 issue、发行列表和仓库元数据；两者均未启用 GitHub Discussions。MacPlay 返回 5 个 issue，PlayPort 返回 2 个；没有找到相同 USB“认证/订阅/视频持续正常但不采用坐标”的报告。

- [MacPlay #5](https://github.com/Roylyl/MacPlay/issues/5)，2026-10-08：USB 已认证并订阅 GGA/RMC，但立即 TEARDOWN、会话断开；无精确 iOS。它是连接失败，不等同于本机持续会话的采用失败。
- [MacPlay #8](https://github.com/Roylyl/MacPlay/issues/8)，2026-10-26：1.2.3（39）无线出画面后断连；[1.2.4 发行说明](https://github.com/Roylyl/MacPlay/releases/tag/V1.2.4)（2026-10-27）修复重复蓝牙握手和再次启动导致断连、旧会话干扰等。没有定位采用修复声明。
- [PlayPort issues](https://github.com/youcci/playport/issues) 涉及触控和 Raspberry Pi，未找到定位问题；[README](https://github.com/youcci/playport) 明确仅无线、不支持 USB，iOS 27 验证范围为连接、视频和触控等。本次发行列表为空。

“没有找到”仅限本次可访问的公开记录，不能解释为没有其他人遇到。

## Apple 官方能确认的边界

| 公开资料 | 可以确认 | 不能由它推导 |
| --- | --- | --- |
| [WWDC16 CarPlay Systems Part 1](https://developer.apple.com/videos/play/wwdc2016/722/)（2016） | 车载卫星位置与手机传感器共同参与定位；CarPlay UI 不显示时会话及位置通信仍可继续；USB 的 iAP2 与音视频的 IP 通道不同 | 视频首帧是系统采用外部位置的通用必要条件；有视频就有位置；认证后强制覆盖；iOS 27 内部选择算法 |
| [isProducedByAccessory](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory)（当前文档，未标发布日期） | 由外部配件提供的位置可标记 true，例子包括 MFi GPS dongle 和 CarPlay | 只要连接配件所有位置都应 true；本机未采集该值时能从发送计数推断它 |
| [isSimulatedBySoftware](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/issimulatedbysoftware)（当前文档） | Xcode GPX 等设备软件模拟与配件来源是不同维度 | 外部配件与 Xcode 模拟共用所有开关或限制 |
| [CLLocation.timestamp](https://developer.apple.com/documentation/corelocation/cllocation/timestamp) 与 [horizontalAccuracy](https://developer.apple.com/documentation/corelocation/cllocation/horizontalaccuracy)（当前文档） | 时间戳表示位置确定时间；水平精度是米制不确定半径，负值表示经纬度无效 | NMEA HDOP 与最终精度的固定换算；更小数值保证覆盖；具体过期秒数和突变拒绝阈值 |
| [Enabling Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)（当前文档） | 模式用于开发功能和本地开发应用；开关流程包含重启 | 必须开启才能使用 CarPlay 外部定位；开启后即可稳定采用外部位置 |

当前官方页面的正文通过 Apple 提供的 Markdown 版本核对。未发现 Apple 发布的 iOS 27.0（24A435）外部位置间歇采用已知问题说明。

## 候选原因与可证伪证据

以下是**调查优先级，不是已确认根因**。本次不执行实验。

| 候选 | 支持与限制 | 能区分它的证据 |
| --- | --- | --- |
| 手机已收到有效外部 fix，但最终定位仍采用其他来源或保留原状态 | LIVI 的手机日志与 Apple 多来源说明支持存在这一层；本机同 SHA 成败交替、目标距真实位置几十至几百公里与来源明显冲突相容，但目前没有手机接收证据，不能推出距离阈值 | 同一时间轴上出现对应 NMEA 接收，随后 native CLLocation 仍为真实点、来源/精度/时间戳可核对；若手机根本没收到，此解释就不能优先成立 |
| 本地接受或入队后，实际发送／ACK／手机解析在某轮失败 | LIVI no-op 与 DiPlay handler 拒绝说明这类边界真实存在；本机成功史排除“永远不发”，不能排除偶发失败 | 对齐命令接受、队列消费、实际写入、链路 ACK、手机 `accessoryd`/`locationd` 处理；不能把任一单层 success 当作最终采用 |
| 订阅、停止或重连的会话归属／在途包问题 | DiPlay #48/#157 有 Start/Stop 及端点实例；本机也有 Stop/Start，但 USB 不走同样无线交接 | 每条订阅与发送关联会话、通道和时间，特别核对 Stop 后排队消息、重订阅后的新请求和手机拒绝原因 |
| NMEA 的时效、一致性或字段语义 | 独立实现强调发送时 UTC 和订阅间隔；DiPlay [#109](https://github.com/shihabal3amri/DiPlay/pull/109)（2026-10-01，0.2.9）修复未知 RMC course 被写成北向；这不是其根因已适用于本机的证据 | 离线比较成功/失败实际字节：UTC 日期/时间、GGA/RMC 同一 fix、校验和、有效标记、精度/卫星/高度、速度和航向、CRLF/NUL、采样年龄。找到确定差异再归因；本机既有相同时间点编码对照降低静态编码错误可能性 |
| Developer Mode 本身导致采用 | 本机 enabled 已同时成功和失败，disabled 也有成功史；Apple 未公开此因果要求 | 现有证据已经否定“enabled 足够”。要证明因果必须隔离重启和其他状态，不能再用单次开关后的结果判断；当前不建议盲目重复开关 |
| 地图缓存或不同应用呈现不一致 | 当前只观察 Apple 地图；旧记录有地图间恢复不同步 | 原生 CLLocation 时间戳/来源与地图时间轴可区分旧显示与新 fix。蓝点不动本身不能说明失败在哪一层 |

最有价值的下一步是先利用已有成功/失败保存资料做离线对照，确定能否补到“实际发送／ACK”的证据。若将来另行授权真机调查，再优先采集手机端接收、拒绝或 CLLocation 来源，而非继续相同报点轮次。手机日志可能被隐私脱敏；没有可见日志也不能反向证明未收到。

## 检索范围与未使用证据

- 检索覆盖 Roylyl/MacPlay、youcci/playport、shihabal3amri/DiPlay 的 issue、相关 PR、README、发行记录；通过原始 GitHub API/连接器读取，而非把搜索镜像当最终来源。
- 扩展到 f-io/LIVI #354、aur3l14no/accessory-location、lvalen91/CPC200-CCPA_resources，并读取 Apple 官方页面。
- 关键词包括 GPS、location、定位、GGA/RMC、NMEA、Developer Mode、iOS 27、ACK、handoff、Stop/Start。
- KKlbs 旧论坛线索的原页本次无法打开，未用于支持结论；卖家说法未用于推导协议或 iOS 选择规则。关于其他尾插的零散成功报告也不能代替本机验收。
- 未找到可公开核验的 iOS 27.0（24A435）完整复现、Apple 内部融合算法、固定“刷新 10 秒必成功”规则或开发者模式必要性结论。
