# Mac 菜单栏与 USB 会话

应用代码已具备本机固定点流程；真实 USB、隐藏画面、锁屏与恢复验收统一留待最终现场测试。自动化测试使用外部假接收进程与服务边界夹具，不代表手机已采用位置。

## 构建

需要 macOS 13+、Xcode Command Line Tools 和 Python 3.9+。

```sh
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open 'build/Location Lab.app'
```

构建生成本地 ad-hoc 签名应用。默认使用 `/usr/bin/python3`；通过环境变量 `LOCATION_LAB_PYTHON` 可指定其他 Python 3 的绝对路径。构建不启动 USB；打开应用只枚举连接设备，明确点击“应用位置”才启动会话。

## 本机运行时配置

先按 USB 隐藏画面验证工具准备一个仓库外的私有工作目录。应用使用其 `resources/` 运行时与 `data/` 本机身份；认证资料不打包进应用。

工作目录需要下列由用户本机提供且有使用权限的材料：

- `data/authentication/identity.pk8`
- `data/authentication/certificate.p7b`
- `data/cp/macplay-v3/identity.json`：既有配件配对身份，保持原实验身份以沿用已验证链路。

不要将私钥粘贴到聊天或提交进仓库。应用不搜索或复制原实验目录。准备好的 `data/` 只供该应用使用，权限为 0700，文件为 0600；原实验目录保持不变。

创建 `~/.config/location-lab/config.json`，仅保存准备目录的绝对路径：

```json
{"runtime":"/absolute/path/to/prepared-workspace"}
```

该配置所在目录建议 0700，文件 0600。每个会话在短路径的私有 `/tmp/ll-*` 目录建立控制 socket 与临时设置，退出时清除，避免 macOS Unix socket 路径长度限制。原始后端输出不保存或显示。

## 操作与状态

菜单栏打开详情，输入 WGS84 纬度、经度。仅一台 USB iPhone 就绪时才能应用。编辑输入只改变草稿；再次点击应用才替换已接受目标。真实后端认证与位置订阅就绪后，使用已有实验的固定点 NMEA 供数路径，以最多 1 Hz 持续提供位置。

页面/窗口关闭不结束会话；菜单栏“停止报点”、系统睡眠或应用退出会结束它。USB 拔线、后端失败、异常调度间断也清空目标。再次连接不会重放旧目标。

详情中的本地接受批次不是手机采用证据。“已观察到目标位置”和“已恢复真实位置”分别记录用户现场观察，程序不自动推断两者。切换目标会清除旧的采用确认。停止之后仍显示恢复待确认，必要时在手机上手动刷新定位服务。

## 开发接口

`location_lab.session.SessionService` 是 Mac 与后续已授权手机操作共享的测试边界。`apply`、`status`、`stop`、`refresh_devices`、`tick`、`suspend`、`shutdown` 和用户观察确认提供外部行为；后端注入只用于系统边界。

原生应用以私有 stdin/stdout JSONL 管道启动 `python3 -m location_lab.local_host`。可用 `--runtime` 指定准备目录，或 `--config` 指定本机配置。管道关闭、SIGTERM 或退出操作会结束 USB 会话。该管道不对局域网暴露，也不替代后续手机配对授权。
