# toAnywhere

个人使用的 iPhone 原生地图控制 App 与 Mac 后台定位服务。支持 USB 与无线控制／报点，连接 USB 时优先使用 USB。

手机现在可以保存多台 Mac 的配对信息：各台电脑首次扫码授权后，App 自动寻找可用电脑，优先 USB，并在当前电脑不可用时尝试其他已配对电脑。设置中可查看、重命名或移除电脑。自动切换连接不会重放目标位置；原电脑的报点尚未确认停止时，会先处理该会话。

当前阶段：**USB 优先双通道已安装并通过短流程：手机关闭 Wi-Fi 后可经 USB 应用与恢复；拔线后无线控制、应用与恢复正常，不自动重放旧目标。长时间及更多异常场景仍待验收。** 详见[当前验收状态](docs/native-app-validation-2026-10-31.md)。

当前 WPA2/WPA3 混合网络已通过类型 3 握手、应用位置和恢复短测；需要配套且摘要匹配的本机运行时。仅 WPA3 网络尚未验收，不自动降为 WPA2。

规格见 [Issue #1](https://github.com/SAMYJ1/toAnywhere/issues/1)，最终现场验收跟踪于 [Issue #9](https://github.com/SAMYJ1/toAnywhere/issues/9)。用户已确定先按既有 USB 路径开发，开发结束后统一真机验证。

## 早期方案记录

- 手机 Safari／主屏幕入口，Apple 地图搜索和点选、WGS84 坐标输入、常用点收藏。
- 手机与 Mac 在同一局域网传递控制指令，位置数据由 Mac 经 USB 提供。
- 首次在 Mac 确认授权，之后由手机直接应用目标；授权可撤销。
- Mac 菜单栏运行，收藏保存在 Mac；手机页面切后台后由 Mac 管理会话。
- USB 断开、Mac 睡眠或退出结束会话；重连后手动应用，不自动重放。
- 停止报点与恢复真实位置分别确认。

## 文档

- [完整应用方案](docs/usb-app-design.md)
- [领域术语](GLOSSARY.md)
- [架构决策：手机控制与 USB 会话分开](docs/adr/0001-separate-phone-control-from-usb-session.md)
- [USB 实测基线与限制](docs/validation-baseline.md)
- [Mac 应用构建与本机配置](docs/mac-app.md)
- [手机配对、持久授权与撤销](docs/phone-control.md)
- [常用点收藏](docs/favorites.md)
- [Apple 地图选点与校准策略](docs/apple-map-selection.md)
- [USB 隐藏画面准备工具](tools/usb_validation/README.md)
- [地图验证工具](docs/map-validation.md)
- [最终真机验收清单](docs/acceptance.md)
- [2026-10-29 USB 真机验证结果](docs/device-validation-2026-10-29.md)
- [2026-10-30 原控制器开启状态复测](docs/device-validation-2026-10-30.md)
- [2026-10-30 Location Lab 应用验收](docs/app-validation-2026-10-30.md)
- [外部位置间歇采用的社区与官方证据调查](docs/research/community-location-adoption-2026-10-30.md)
- [赛银国际广场：老链路与应用附近点成功对照](docs/saiyin-validation-2026-10-30.md)
- [隐藏模式修复与附近点验收](docs/hidden-mode-validation-2026-10-30.md)
- [无 USB：Wi-Fi＋蓝牙与纯蓝牙验证](docs/wireless-validation-2026-10-30.md)

## 构建与运行

```sh
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open 'build/toAnywhere.app'
```

应用默认不启动定位会话。按本机配置说明提供隔离运行时与局域网地址后，手机才能通过二维码请求授权；只有明确应用位置才会启动 USB 会话。

应用不包含第三方运行时或认证资料；本机配置和现场验收步骤见各工具说明。地图令牌、实际局域网入口、隐藏画面后的稳定性及坐标校准仍待验证。


## 原生 App 迭代

2026-10-30 用户确认原生 iPhone App＋Mac 后台无线方向。2026-11-02 扩展为 USB 优先的双通道，手机控制与位置报点均支持 USB，沿用已有配对。关闭 Wi-Fi 的 USB 短流程及拔线后的无线短流程已通过；两小时验收尚未完成。

- [已确认需求](docs/native-app-design-interview.md)
- [当前实现与验收状态](docs/native-app-validation-2026-10-31.md)
- [双轴代码审查](docs/native-app-review-2026-10-31.md)
- [无线运行时准备](tools/wireless_validation/README.md)
