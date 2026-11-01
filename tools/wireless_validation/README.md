# 无线隐藏运行时准备

从用户已提供的可见运行时创建仓库外独立覆盖：

```sh
python3 -m tools.wireless_validation.prepare --resources /absolute/source/resources --output /absolute/new/private-workspace
node tests/verify-discovery.cjs /absolute/new/private-workspace/resources/engine/discovery.js
```

保留真实解码、隐藏展示，并在建连前初始化媒体插件。修正 macOS/libuv 的 IPv6 接口作用域、未知目标探测和多播失败状态。`hidden-video.patch` 与 `wireless.patch` 分别记录两个阶段；`preparation.json` 保存最终哈希。

工具不启动接收器，不复制认证资料。指定输出必须是新目录；源资源保持不变。实际 helper 能否支持当前网络安全类型须另行验证。

验证脚本加载实际 discovery 模块，并将网络依赖替换为内存对象，验证作用域、目标约束及失败处理；不会产生网络 I/O。通过该脚本不等于真机已连接。
