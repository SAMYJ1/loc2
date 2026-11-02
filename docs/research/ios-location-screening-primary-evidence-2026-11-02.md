# iOS 外设位置筛选：一手资料与公开逆向证据

调查日期：2026-11-02。范围为公开资料只读核对与文档整理；未连接手机、报点、修改设备设置、运行第三方实现或发布外部消息。沿用仓库“报点／位置采用／恢复真实位置”的术语。本记录补充 [10 月 30 日社区调查](community-location-adoption-2026-10-30.md)，重点调查 `CLNmeaScreener`、`positionDiffBound`、`positionDiffBoundMediumIntegrity` 和 `locIntegrity`，不重复原来的链路排障清单。

## 结论

**找到了包含本机同名日志字段的公开 `locationd` 反编译材料。它为“筛选条件随参考位置和系统状态变化”提供了具体代码证据，但材料标注的是 iOS 26.1（23B85），不能当作本机 iOS 27.0（24A435）的完整实现证明。** 该材料是作者生成的 Hex-Rays 伪代码，既不是 Apple 发布的源代码，也没有在本轮与原始 IPSW／机器码重新核验。[仓库及版本](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore)、[固定提交](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/commit/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab)

可建立的判断是：

- **15 km 不是已证实的通用硬上限。** 旧版本伪代码中的主阈值是“随时间和参考精度增长的数值”与一个存储下限取最大值；此函数没有把结果上限夹到 15 km。本轮未从公开常量表恢复出 7 km／15 km 的初始化值，不能声称这两个常量在 26.1 源码中已经证实。[距离判断](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7433-L7449)
- **`positionDiffBoundMediumIntegrity` 与主接纳阈值是两套计算。** 旧版本函数先根据较小的界限写入完整性数值，再独立返回是否超过主界限；因此 `locIntegrity=25` 本身不等于筛选失败，也不能把它解释为 GGA fix quality=25。[完整性函数](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7397-L7430)、[布尔返回](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7538)
- **公开旧版代码具有参考位置有效期、参考来源选择、参考坐标系处理、频率检查和连续成功／失败状态。** “只看两点距离”和“证书通过就一定采用”都不足以描述这个路径。[参考选择](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8023-L8143)、[状态计数](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8145-L8202)
- **没有参考位置时，旧版代码存在 `not screened` 分支。** 这使“同一实现有时接受很远的点、有时拒绝较近的点”在机制上并不矛盾；但本轮没有证明定位服务开关会清空什么状态，也没有成功轮次的当前版本手机日志，不能把历史约 200 km 成功归因于该分支。[无参考分支](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8023-L8095)、[`not screened` 日志选择](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7798-L7820)

## 来源等级与版本

| 来源 | 日期／版本 | 本轮确认的证据性质 | 限制 |
| --- | --- | --- | --- |
| [EthanArbuckle：`iPhone18-3_26.1_23B85_Restore`](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore) | 固定提交 `90aa0cfe59d9682b4265e1354c8b19ec3c7823ab`，2025-12-07；提交说明为重新生成并改进类型信息 | 仓库自述为各 iOS 二进制的 Hex-Rays pseudocode；含具体算术、控制流、原始日志字符串 | 作者提供的反编译产物，不是官方源码；变量类型／指针算术可能失真，缺少部分常量数据；不是 27.0 |
| [blacktop/ipsw-diffs：iOS 18.2 beta 比较](https://github.com/blacktop/ipsw-diffs/blob/8af66bf3a924930979237d896ee447f0f2684ac8/iOS/18_2_22C5109p__vs_18_2_22C5125e/MACHOS/locationd.md) | `22C5109p → 22C5125e`；locationd `2953.0.19.0.0 → 2953.0.25.0.0` | 二进制字符串差异出现“input frequency too high”筛选失败日志 | 证明字符串变化，不证明检查首次引入时间或所有分支语义 |
| [blacktop/ipsw-diffs：iOS 18.4 beta 比较](https://github.com/blacktop/ipsw-diffs/blob/8af66bf3a924930979237d896ee447f0f2684ac8/iOS/18_4_22E5200s__vs_18_4_22E5216h/MACHOS/locationd.md#L207) | `22E5200s → 22E5216h` | `verifyWithExternalLocation` 的诊断签名新增 `bool &` 参数 | 只证明这个版本间可见签名改变，不能自行给布尔参数命名 |
| [Apple WWDC16：Developing CarPlay Systems, Part 1](https://developer.apple.com/videos/play/wwdc2016/722/) | 2016 | 车载 GNSS 与 iPhone 传感器共同用于定位；车速用于航位推算 | 没有发布上述私有筛选阈值或选择算法 |
| [Apple：`isProducedByAccessory`](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory) | 2026-11-02 读取当前文档 | Core Location 的结果来源可标为外部配件，包括 MFi GPS dongle 与 CarPlay | 不是接纳承诺，也不公开私有 `type` 数值映射 |

## 旧版本伪代码能支持的精确规则

以下仅对上述固定提交中的伪代码作静态解读。变量名称中 `hunc`、`timeDiff`、`maxSpeed`、`positionDiffBound` 来自同一函数日志参数对应关系；`storedFloor` 和 `storedExtra` 是本文为未命名成员添加的描述，不是恢复出的官方成员名。

### 1. 主距离界限是带下限的动态容差

`ExternalLocationData::isLocationWithinBoundsAndSetLocIntegrity` 对应 `sub_100711508`。结合算术与紧随其后的日志参数，规则可归纳为：

```text
dt = abs(currentTime - referenceTime)
candidate = abs(dt * maxSpeed) + referenceHorizontalUncertainty
positionDiffBound = max(candidate, storedFloor)
distancePass = (positionDifference <= positionDiffBound)
```

证据位置：[7433–7449 行的计算](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7433-L7449)、[7458–7488 行的变量到日志字段对应](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7458-L7488)、[7538 行的返回](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7538)。

这里的 `hunc` 属于**被选作比较基准的参考位置**，并非从该句 GGA 直接读出的 HDOP。`fillData` 从系统位置通知填充该结构，并将水平不确定度限制为非负数；日志也使用 `fHorizontalUncertainty` 命名。[填充函数](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_20.mm#L8466-L8508)

该版本调用方按一个尚未确定语义的状态字节，在 `50.0` 和 `100.0` 中选择传给此函数的 `maxSpeed`；本轮没有找到足够依据，把这个字节命名为“车辆信任”“正在驾驶”或“证书等级”。它也不是这一函数直接读取的 RMC 实测速度。[调用方](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8101-L8142)

### 2. 完整性数字由另一个界限计算

同一对象的 `sub_1007113EC` 为：

```text
mediumBound = abs(dt * 15.0) + referenceHorizontalUncertainty + storedExtra
locIntegrity = 50 if positionDifference <= min(positionDiffBound, mediumBound)
               25 otherwise
```

这段代码把 `mediumBound` 打印为 `positionDiffBoundMediumIntegrity`，把结果打印为 `locIntegrity`。上层把结果写入完整性输出参数，而距离函数仍独立返回 `positionDifference <= positionDiffBound`。[完整性计算及日志](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7397-L7430)、[调用](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7449)

由此可推导一个有限结论：当 `mediumBound < positionDifference <= positionDiffBound` 时，这个距离函数可以返回通过，同时完整性值为 `25`。**因此不能单靠 `25` 判定失败；必须同时看筛选结果。** 本文不把 `25`／`50` 翻译成 Apple 未公开的完整性枚举名称，也不声称它们等于 NMEA quality、mode 或 HDOP。

构造函数给参考记录分配不同的 `storedExtra`。例如，参考选择分支输出数字 `4` 时使用对象偏移 `+200` 的记录；该记录的 `+56` 成员位于对象 `+256`，初始化位型为 `0x40B3880000000000`，按 IEEE 754 double 解码为 **5000.0**。两个输出数字 `1` 的记录，其相应位型为 `0x4069000000000000`，解码为 **200.0**。这是旧版伪代码中可核对的常量关系，不是对当前 iOS 的 `type` 枚举命名。[构造函数](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7541-L7582)、[记录选择](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8033-L8054)

**未恢复的部分：** 主界限的下限成员来自 `xmmword_101C8A2xx` 数据符号，公开 `.mm` 文件没有在此展开这些常量。本轮没有为了补齐它们下载 IPSW、安装逆向工具或读取私人设备二进制，不能从名字或本机日志反填这些常量。

### 3. 参考位置选择具有有效期，并存在无参考通路

`sub_100712514` 把输出类型先设为 `0`、完整性初值设为 `50`，然后按顺序选取参考记录：

1. 一个特殊条件组合要求状态字节、`goodGNSSTracking` 相关标记、额外时间／不确定度条件，以及参考时间差小于 3 秒；选取第二个记录，输出类型数字 `1`。
2. 否则，第一记录与当前时间之差小于 3 秒时，选取第一记录，输出 `1`。
3. 否则，第三记录的时间差小于 1800 秒时，选取该记录，输出 `4`。
4. 否则，第四记录的时间差小于 1800 秒时，选取该记录，输出 `6`。
5. 都没有可用参考时，打印 external location unavailable，日志列出 gps／wifi／cell／LAC 的参考时间，然后返回真，输出类型仍为 `0`。

这些是该文件的分支条件，不是新的设备试验。本轮保留数字值，不把它们直接翻译成本机 27.0 的来源名称。[选择及返回](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8023-L8103)、[`goodGNSSTracking` 填充日志](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_20.mm#L8648-L8671)

随后仍有状态门控；成功路径在输出类型为 `0` 时把日志文本从 success 换成 not screened。因此“无参考时可能通过未筛选通路”有静态代码依据，但“无参考一定成为最终系统位置”仍不成立。引用者还应注意 `screenData` 后续不等同于完整的 Core Location 融合和 App 采用。[调用、状态门控及日志](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7780-L7820)

定位服务开关、重启、关闭 Wi-Fi 可能改变参考数据可用性，是待验证假设；本轮没有证据证明任何一种操作必定使上述记录失效，或保证之后一定采用远处目标。

### 4. 还有坐标、时间、频率和状态检查

| 检查 | 伪代码中直接可见的证据 | 不应扩大成的结论 |
| --- | --- | --- |
| 坐标有效性 | invalid accessory coordinate 分支返回失败；[7703–7744 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7703-L7744) | 坐标语法合法就会采用 |
| 时间检查 | 有条件比较位置数据时间与 build time；[7746–7777 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7746-L7777) | 所有日期问题只有这一个检查 |
| 输入频率 | 通过前面条件后，有一条分支要求相邻有效数据时间差至少 0.8 秒，否则输出 input frequency too high；[7780–7789 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7780-L7789)、[7884 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7884) | 任意 TCP/iAP2 包必须相隔 0.8 秒；本机 1 Hz 必定通过所有检查 |
| 连续状态 | `sub_100712870` 有条件更新连续成功／失败计数并改变门控值；[8145–8202 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8145-L8202) | 从重复失败次数就能推导黑名单、封禁时长或恢复等待时间 |
| 参考坐标系 | 比较参考与输入 frame，存在转换及不能匹配时返回真的分支；[8114–8142 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L8114-L8142) | 可以随意改 frame 来保证系统采用；或数字 `2` 的当前版本含义已确认 |
| 暂停状态 | paused 分支停止此路径；[7988–8007 行](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_98.mm#L7988-L8007) | 存在已证实的、按认证证书维持的永久信任评分 |

### 5. 筛选存在配置与情境开关，但尚未定位到产品身份差异

同一固定版本的配件位置提供器会读取 `AccessoryConfig` 的 MobileAsset 配置，然后取出以下参数：`getEnableAggressiveLocationScreening`、`getLocationDiffThresholdForAggressiveScreening`、`getMinContinuousFailureCountForBlockingAccessory`、`getMinContinuousSuccessCountForUnblockingAccessory`、`getMaxGPSUncertaintyForAggressiveBlockingAccessory`，以及 course screening、GGA-only 和 CarPlay DR mode 的相关参数。后续日志明确打印这些参数。[配置加载](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_97.mm#L8845-L8862)、[配置日志](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_97.mm#L8884-L8914)

这支持“算法不只由一组固定距离常量决定”，但不证明本机当前加载过哪些配置，也不能直接把 aggressive threshold 等同于打印出的 7 km／15 km 下限。沿对象偏移追踪，前述控制 `maxSpeed` 的状态字节还受多个提供器状态组合写入；其中至少涉及 aggressive-screening 配置，但其他输入的完整语义未恢复，本文不将它命名为车辆信任。[状态更新](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_97.mm#L7025-L7059)

另有日志直接标注 `airborne,1` 时关闭 `EnableAccessoryNMEAScreening`，反向情境重新开启，两处均改写筛选 enable 字节并重置筛选状态。这是**存在情境开关**的旧版代码证据，不是对如何人为触发它的建议，也没有证据把它与本案、任何具体定位器或某类认证证书对应起来。[关闭分支](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_27.mm#L3437-L3461)、[开启分支](https://github.com/EthanArbuckle/iPhone18-3_26.1_23B85_Restore/blob/90aa0cfe59d9682b4265e1354c8b19ec3c7823ab/usr/libexec/locationd/locationd_35.mm#L7125-L7149)

**这里的内部 `airborne` 状态不等于 Settings 中的“飞行模式”无线电开关。** 本轮未恢复其分类器与触发来源，不能把两者联系起来。

本轮没有找到足够明确的调用点，能证明“CarPlay 与独立 MFi GPS 配件必定使用不同的距离规则”，也没有找到可据以解释本机 `accessoryType=70` 的公开完整枚举。Apple 文档同时把 MFi GPS dongle 与 CarPlay 列为外部配件来源，只说明它们可产生这一类来源标志，不能推出二者协议、能力申报、配置与筛选路径完全一致。[Apple 来源属性](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory)

## 与本机 iOS 27.0（24A435）证据的关系

本段的设备事实来自 [本机验收记录中的 11 月 1–2 日补充](../native-app-validation-2026-10-31.md) 与本轮主任务提供的脱敏手机日志摘要；本研究子任务未自行读取私人原始日志，也没有重新做设备试验。

- 约 23.1 km 的报点轮次在手机筛选日志中全部 87 次失败，当时主界限为 15 km。
- 另一个时间窗出现主界限 7 km，用于筛选的类型数字为 `1`，之前窗口为 `4`。这是不同观测窗口／会话的对比，不能写成同一会话内门槛变化；类型名称和因果关系尚未由当前版本实现核实。
- 用户手动开关定位服务后，上海虹桥目标距离约 156.28 km 的一轮仍为 54/54 失败，主界限 15 km，类型数字 `4`。
- 对应 `positionDiffBoundMediumIntegrity` 约 5.056–5.476 km，`locIntegrity=25`。
- 用户另有约 200 km 上海目标在 USB、1 Hz、开关定位服务后成功采用的历史观察；该成功轮次缺少与上述失败轮次同级的筛选器日志。
- 11 月 1 日后续，用户另报告手动刷新定位服务后已采用约 23 km 外的目标；同样没有同步采集开关前后的筛选内部日志。

因此，当前设备证据已经比 10 月 30 日的“仅本地入队”更强：本轮失败可以定位到**手机接收之后的筛选阶段**。它不能追溯证明历史成功为何发生，也不能把当前 15 km 推广为所有时间、所有参考状态或所有 iOS 版本的限制。

本轮主任务另做了 **141 组现存日志记录的离线数值核对**，没有新设备试验：23 km 轮次的 87 组，`mediumBound − 15 × abs(timeDiff) − hunc` 为 **4999.93–5000.08 m**；156 km 轮次的 54 组为 **4999.93–5000.07 m**。全部 141 组的 `abs(timeDiff × logged maxSpeed) + hunc` 均低于打印出的 15000 m 主界限。微小残差范围来自已打印字段的小数精度；结果与旧版公式、5000 m 附加量及下限分支数值吻合，但不能证明整个 27.0 实现完全相同。[脱敏数值摘要](location-screening-numeric-check-2026-11-02.json)

## 社区原始案例：哪些能补充，哪些不能

| 一手来源 | 直接观察／实现事实 | 作者解释或不能证明的部分 |
| --- | --- | --- |
| [LIVI #354](https://github.com/f-io/LIVI/issues/354)，2026-09-21；iOS 18.7.2，USB，macOS 14.6.1，基线 `00936397` | 修复发送空实现后，手机出现 `onAccessoryNmeaReceived`；缺乏手机自有定位时，日志出现 Accessory 来源且 Maps 跟随附近移动点；作者报告远跨洲坐标短暂生效后停止 | “iOS 发现 spoofing／重新信任”的说法是作者解释；Wi-Fi、蓝牙、飞行模式与重启同时调整，不能归因单个开关或推导距离阈值 |
| [DiPlay #157](https://github.com/shihabal3amri/DiPlay/pull/157)，2026-10-03；iPhone 17 Pro Max，iOS 27.0.1，无线，PR head `f75fce6927de81879cf4a040072327a35daaa92c` | `accessoryd` 表示蓝牙已占位置端点，Wi-Fi 的 633 条消息被拒；修复声明归属后请求获接纳；USB 路径未改 | 这是端点归属／传输接纳问题，不能替代本机 CLNmeaScreener 距离拒绝的解释；接纳位置消息也不等于每个坐标最终采用 |
| [DiPlay #48](https://github.com/shihabal3amri/DiPlay/pull/48)，2026-09-29 至 09-30；iPhone 15 Pro，iOS 27 未给 build，基于 0.2.7 | 发现报点突发、Stop 后排队消息、Android 后台失去 fix；PR 自述没有核实 iOS 位置采用 | 早期跨链路延续订阅方案后来被 #157 替代；其 1 Hz 修复不能证明距离筛选必定通过 |
| [DiPlay #109](https://github.com/shihabal3amri/DiPlay/pull/109)，2026-10-01；BYD Tang 2024，无线，未给 iPhone/iOS 完整版本 | 没有 bearing 时，RMC course 从 `0.00` 改为空；作者报告停车／移动地图位置正常 | 修正的是“未知朝向不应编码为朝北”，没有给出朝向与距离阈值的因果证据 |
| [accessory-location README](https://github.com/aur3l14no/accessory-location/blob/8a13296a3d81dae18ad4481e7a9eca913c2c644f/README.md)，2026-10-15 固定提交 | 独立 USB 工具区分认证、订阅、链路 ACK 和地图位置采用；记录 ACK 后仍不移动的排障情况 | 开关定位服务是作者排障建议，README 同时承认仍可能拒绝；没有公开当前 iOS/build 的完整矩阵，也不读回手机最终来源 |

这些案例与历史上偶发的远距离采用并不矛盾。它们共同支持分层观察，尚不足以证明“连续发足够久”“修改 GGA 精度”“伪装某车型”或“更换认证身份”就能绕过当前筛选。

## HHJ Pro 比较的边界

用户本轮已明确品牌为 **HHJ Pro**，并确认历史成功发生在 **iOS 27**；尚无完整 27.x／build 以及是否同一台手机的已确认记录。因此，不能用“HHJ 成功只是因为旧 iOS”解释这个差异。历史成功是用户观察证据，仍须与产品内部实现证明分开。

“同属 MFi，所以应该完全相同行为”也不能由公开资料推出。Apple 的 MFi 计划涵盖 CarPlay、iAP2、认证协处理器等多种技术，产品计划、开发、认证是分开的环节；Core Location 则把 MFi GPS dongle 与 CarPlay 都列为可能的外设来源。两者都属于外设来源或都能完成某次认证，并没有证明其协议路径、能力申报、会话状态及手机端配置相同。[MFi 流程及技术范围](https://mfi.apple.com/en/how-it-works)、[位置来源属性](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory)

制造商 Bad Elf 的原始兼容公告提供了一个有版本边界的反例：它报告 iOS 26.1 忽略老款 iAP1 GPS 配件的 Core Location 数据，而较新产品在少量情形下受 Wi-Fi 状态影响，系统没有选用外部位置；其公告后续标注老款 iAP1 问题在 26.3 修复。这说明“都是外设 GPS”不足以保证相同接纳行为，但**不是 HHJ Pro 的协议证据，也不是 iOS 27 的筛选规则**。[Bad Elf 原始兼容公告，26.1 状态更新于 2025-11-18、26.3 更新于 2026-02-12](https://bad-elf.com/pages/cleared-to-update)

本研究没有获取 HHJ Pro 固件、认证材料、iAP 识别能力列表或手机端筛选日志；不能认定它使用或绕开此处反编译路径，更不能声称认证证书本身带有绕过距离筛选的权限。

另查到 HHJ Pro 的原始使用反馈：在 [LINUX DO 主题的 19–22 楼](https://linux.do/t/topic/2195315/19)，一位使用者报告数分钟后回到原位置，另一位建议关闭 Wi-Fi 并刷新定位服务；前者随后表示按此操作仍会约五分钟后失效。该主题发帖者提到 iOS 26.5，但不能把发帖者的版本自动套给每位回帖者。它是带操作过程的个人反馈，不是受控试验，也没有筛选器日志；不过它足以反驳“尾插一旦连上就永远稳定覆盖”的泛化。[讨论全文](https://linux.do/t/topic/2195315)

[HHJ 产品说明站](https://hhjpro.com/zh-tw/)和[使用指南](https://hhjpro.com/en/guide)描述 Lightning／USB-C 双接口、配套 App 选点及恢复步骤，没有公开足以核验此问题的协议实现、识别能力、筛选参数或认证身份。网站与具体硬件制造主体的关系未独立核实。另一个名为 [Remychou/HHJ-Pro](https://github.com/Remychou/HHJ-Pro) 的公开仓库，本次读取根目录只包含 38 字节 README；不能当成 HHJ 固件开源或 MFi 认证证据。

当前 loc2 的日常路径需要 Wi-Fi 建立 CarPlay 网络会话，而部分尾插使用反馈包含关闭 Wi-Fi 的操作。这是值得做控制对照的条件差异，不是本轮已证实的唯一根因，也不应直接在当前无线链路关闭 Wi-Fi 后把断线误当成筛选器行为。若继续实测，优先在相同手机／完整 iOS build 下对照 HHJ 与 loc2 的 `onAccessoryNmeaReceived`、筛选开启状态、参考类型／时间／阈值、`success`／`not screened`／失败及实际位置来源；仅记录必要的脱敏字段，不需要公开认证私钥。本轮没有执行这类新设备对照。

## 仍未确定的事项

1. 本机 27.0（24A435）各参考类型、完整性枚举、下限常量与选择优先级的完整定义；本文不借旧版数值推测当前枚举名称。
2. 固定下限 7 km／15 km 的配置来源、是否被远程配置或其他状态改变；旧版 `.mm` 中未展开的常量不能冒充已恢复值。
3. `maxSpeed` 的状态字节完整来源，以及车辆运动、车辆能力、GNSS 质量是否通过它间接改变筛选；Apple 仅公开描述融合与航位推算，没有公开此字节语义。
4. GGA quality、RMC mode、卫星数、HDOP、车速、朝向分别如何影响后续融合或完整性。已读的上述完整性辅助函数没有直接接收这些 NMEA 字段，不能据此推荐修改它们。
5. 手机是否为某个配件身份保存跨会话“信任”、其持续时间与重置条件。连续状态计数的存在不等同于证书黑名单，也不证明认证类别决定筛选界限。
6. 历史约 200 km 成功采用时的参考位置可用性、类型、阈值、是否走 not screened 分支、最终 CLLocation 来源。没有成功轮次日志，就不能把一致性假设升级为根因结论。

检索范围包括 Apple 官方 CarPlay/Core Location 资料、GitHub 全局精确字段搜索、上述原始 Issue/PR/源码、公开符号／日志记录。没有找到官方发布的 7 km／15 km 策略说明。普通网页搜索未找到字段解释，不代表该机制没有其他非公开资料；GitHub 代码检索在本轮确实找到了更强的旧版逆向证据。
