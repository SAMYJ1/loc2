# 手机首次配对与控制

手机控制页与 Mac 菜单栏共享同一个会话服务。局域网服务只接受配对、状态、应用和停止操作；Mac 确认授权通过本机进程 stdin/stdout 完成，没有浏览器管理接口。手机页面退出、后台或失去 Wi-Fi 不会结束已经接受的 USB 会话。

## 本机配置

在私有 `~/.config/location-lab/config.json` 中保留已有运行时配置，并增加：

```json
{
  "runtime": "/absolute/path/to/prepared-private-runtime",
  "phone": {
    "bindAddress": "192.168.1.23",
    "advertisedHost": "192.168.1.23",
    "port": 8765
  }
}
```

例子中的 IPv4 只是示例，必须替换为这台 Mac 当前实际使用的局域网 IPv4。服务只绑定这个明确地址，不默认监听所有网卡；`advertisedHost` 是手机实际访问的主机名或地址，配合端口构成唯一允许的 Host/Origin。可使用能在手机解析到这台 Mac 的稳定局域网主机名。地址变化后更新配置并重新打开应用。为使浏览器继续使用同一个站点，建议保持访问地址稳定。

Mac 应用需运行，手机与 Mac 需同网且该地址可达。Mac 关闭后，手机控制页无法访问；本版不承诺离线页面或公网访问。缺少配置时 Mac 本地功能仍可使用，配对窗口会显示提示。

本步骤不复制 USB 认证资料或私钥，也不改变运行时身份准备方式。地图 token 由地图接入配置提供。

## 首次使用

1. 连接且仅连接准备授权的 USB iPhone。
2. Mac 菜单选择“配对手机控制端”，显示绑定目标手机的二维码。
3. 手机扫码打开控制页，页面显示“等待 Mac 确认”。
4. Mac 的配对窗口核对待确认控制端及目标 USB 手机，点击“允许所选控制端”。控制端名称是浏览器声明，不作为设备身份证明。
5. 手机准备 WGS84 草稿，点击“应用位置”。未接线时仍能编辑草稿，但不能应用。
6. 手机或 Mac 都可停止报点。停止后单独检查真实位置恢复；页面不将报点计数当作位置采用。

二维码短时有效且只能发起一次请求。失败或过期时在 Mac 生成新二维码。浏览器获得 HttpOnly、SameSite=Strict、最长保存一年的控制 Cookie；Mac 保存对应凭据哈希与目标绑定，重新打开应用后授权仍有效，但目标位置和定位会话不会恢复。浏览器清除网站数据、Cookie 到期或 Mac 撤销后需要重新配对。Safari 与主屏幕入口是否共享该 Cookie 仍需真机验证，必要时分别配对。

## 持久授权与撤销

默认授权文件是本机配置同目录下的 `grants.json`（通常为 `~/.config/location-lab/grants.json`）。可在顶层配置 `stateDirectory` 指定另一个绝对路径；授权与收藏使用各自独立文件。

授权目录应为当前用户所有且权限 0700，授权文件为 0600。写入通过私有临时文件、fsync 和原子替换完成。文件仅保存高熵随机凭据的 SHA-256 哈希、不可用于登录的授权标识、绑定设备、控制端声明名称和创建时间；不保存原始 Cookie、请求队列、会话、目标、epoch 或 revision。

Mac 配对窗口列出已授权控制端，可点击“撤销所选控制端授权”。撤销后该 Cookie 的下一次请求被拒绝并清除，手机重新显示配对入口；已有定位会话仍由 Mac 管理，撤销授权与停止报点是独立操作。管理授权只通过本机 IPC `pairing-status` / `pairing-revoke`，没有 HTTP 管理路由。

损坏、超限、符号链接或权限不安全的授权文件会使手机服务停用，原文件保持不变，本机停止入口仍可用。先在 Mac 修复文件权限或备份并移除损坏文件后重新配对。若撤销写盘失败，当前进程立即拒绝全部手机控制并报告未能保存；修复授权文件前不要依赖重启保持该次失败的撤销结果。

## 请求契约

- `GET /api/status`：已授权控制端的设备及会话状态。
- `POST /api/pair/request`：二维码 challenge、浏览器随机 pollSecret、声明 label。
- `POST /api/pair/poll`：requestId 与 pollSecret；Mac 批准后设置控制 Cookie。
- `POST /api/apply`、`POST /api/stop`：deviceId、requestId、timestamp、expectedRevision、expectedEpoch；应用额外传 point。
- point 当前为明确 WGS84 手工坐标，保留来源及归一化坐标字段。

二维码 challenge 置于 URL fragment，页面读取后立即清除；不进入 HTTP URL 或服务日志。配对 polling secret 与控制 Cookie 分离。待确认、批准和拒绝只通过本机 `pairing-create`、`pairing-status`、`pairing-approve`、`pairing-deny` JSONL 操作。

控制请求在同一个会话锁内校验授权、目标、30 秒时效（最多允许 5 秒客户端超前）、唯一请求 ID 、`controlRevision` 和本次进程的随机 `controlEpoch` 后执行。本机应用/停止及 USB 设备集合变化同样更新 revision，避免断线重连后的旧初始请求重新执行。重放请求拒绝，不重复执行；进程重启后旧 epoch 的请求同样拒绝。

服务验证 Host 与 Origin，要求 JSON POST、有限请求体；静态文件使用固定白名单。不暴露后端 socket、原始凭据或其他目标手机的活动会话。

## 后续扩展接口

Python `PhoneControl(service)` 持有共享 `SessionService`；HTTP 层始终通过此控制边界执行操作。`state_dir` 指定私有持久化目录。授权与收藏按绑定设备隔离，地图只在本机校准策略成立后扩展坐标提供方校验。

页面提供 `window.locationLab` 的 `setDraft(point)`、`getDraft()`、`getState()` 和 `request(path, body)`，并派发 `locationlab:draft`、`locationlab:status`。`selection-tools` 是新增选点入口的容器。任何入口只改变草稿，明确点击应用才改变会话。

## 验证

```sh
python3 -m unittest discover -s tests
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node tests/browser/phone-control.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node tests/browser/persistent-authorization.mjs
sh scripts/build-mac-app.sh
```

浏览器测试自动启动仅含合成 USB 后端的 loopback fixture，通过同一 private dispatch 完成 Mac 批准。覆盖授权前拒绝、一次性二维码、Cookie、未接线草稿、重连明确应用、草稿隔离和停止；HTTP 测试还覆盖错误目标、旧 revision、过期与重放请求、Host/Origin 拒绝和其他手机会话隔离。

这些检查不启动真实 USB。手机 Safari、主屏幕入口、二维码扫描、局域网网络条件与持续 USB 会话仍归最终真机验收。

地图选点现已接入独立模块；本机令牌和坐标策略、授权配置接口及现场校准边界见 [Apple 地图选点](apple-map-selection.md)。

持久授权浏览器检查覆盖保存 Cookie、关闭浏览器页面、离线控制连接、独立服务进程重启后授权保留但会话不恢复、本机撤销及重新配对。该检查使用 Chromium 和合成后端，不替代 Safari／主屏幕真机验收。
