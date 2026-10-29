# Location Lab

个人使用的 USB iPhone 定位应用项目：手机网页选择目标位置，Mac 接收控制指令并通过 USB 配件链路提供位置。

当前阶段：**附近固定点已在老链路和 Location Lab 应用可见模式下成功对照，完整应用验收仍未完成。** 当前开发者模式开启；赛银国际广场附近点已采用并恢复，但此前远距离目标结果不稳定，隐藏模式、关闭状态和长期运行仍待验证，不能推定全部场景可用。

规格见 [Issue #1](https://github.com/SAMYJ1/location-lab/issues/1)，最终现场验收跟踪于 [Issue #9](https://github.com/SAMYJ1/location-lab/issues/9)。用户已确定先按既有 USB 路径开发，开发结束后统一真机验证。

## 已确定的体验

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

## 构建与运行

```sh
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open 'build/Location Lab.app'
```

应用默认不启动定位会话。按本机配置说明提供隔离运行时与局域网地址后，手机才能通过二维码请求授权；只有明确应用位置才会启动 USB 会话。

应用不包含第三方运行时或认证资料；本机配置和现场验收步骤见各工具说明。地图令牌、实际局域网入口、隐藏画面后的稳定性及坐标校准仍待验证。
