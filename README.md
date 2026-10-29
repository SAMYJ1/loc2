# Location Lab

个人使用的 USB iPhone 定位应用项目：手机网页选择目标位置，Mac 接收控制指令并通过 USB 配件链路提供位置。

当前阶段：**方案已确认，尚未开始应用实现。** 已有 USB 短时固定点行为验证，新应用的完整流程仍需开发和验收。

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

下一步先验证隐藏 CarPlay 画面后的稳定性、Apple 地图在实际局域网入口的可用性及坐标校准，再推进 Mac 应用与手机控制页面。
