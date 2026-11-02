# Mac 常用点收藏

手机控制页的“常用点”将当前选点草稿保存到 Mac；再次选择只载入草稿，仍须明确点击“应用位置”。删除收藏不停止或修改正在报点的目标。

收藏文件与配对授权文件分开存储。生产入口使用本机配置的 `stateDirectory`，默认是私有配置文件所在目录（通常 `~/.config/loc2`），收藏文件名为 `favorites.json`。写入采用同目录临时文件、0600 权限、fsync 和原子替换；损坏或符号链接文件明确报错，不静默重置。

同一个目标手机的已授权控制端共享其常用点；其他目标手机的授权不能读取或删除这些条目。每台手机最多保存 100 个常用点，名称 1–80 个字符。当前实现由单个 Mac 应用进程管理该状态目录。

保存时保留 `provider`、`inputCRS`、`inputCoordinate`、`normalizedWGS84` 等元数据。未校准 Apple 地图点保持 `unverified-mapkit` 和空归一化坐标，可作为草稿保存；保存收藏本身不证明完成校准。应用时仍走主会话的坐标与本机地图策略检查，不会因为来自收藏而绕过校验。

## 接口

- `GET /api/favorites`：读取当前授权目标的列表。
- `POST /api/favorites/add`：名称和完整草稿 point。
- `POST /api/favorites/remove`：favoriteId。

变更请求复用控制命令的 Cookie 授权、deviceId 绑定、唯一 requestId、时效、expectedRevision 和 expectedEpoch 校验。客户端不能自行指定收藏所属目标。列表和变更结果只返回该授权目标的 favorites。

## 验证

```sh
python3 -m unittest discover -s tests -p test_favorites.py
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node tests/browser/favorites.mjs
```

HTTP 验证覆盖重新创建控制器后的持久读取、权限及跨目标隔离、重复请求、未知坐标参考系保留、损坏或链接文件拒绝、存储失败不返回假成功。浏览器流程覆盖收藏草稿、选择不影响当前会话、明确应用、重新加载页面和删除。测试仅使用合成 USB 后端，不执行真实报点。
