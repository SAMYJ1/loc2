# Apple 地图接入验证工具

这是 #3 的独立验证入口，不连接 USB，不应用位置，也不是生产控制页。
当前没有 Maps token 或 iPhone 现场观察；实际地图加载、搜索、手机局域网可达性和坐标校准保持待验收，移交完整个人使用验收任务统一检查。

## 启动

需要 Python 3，无运行时第三方依赖。在仓库根目录执行：

```sh
python3 tools/serve-maps-validation.py
```

Mac 打开 `http://127.0.0.1:8766/` 可验证手工输入。手机验证时，停止该服务并以 Mac 实际局域网 IPv4 地址运行：

```sh
python3 tools/serve-maps-validation.py --bind <Mac局域网IPv4>
```

两端同网，Safari 打开终端显示的 URL。服务仅提供三个静态资源，不提供目录列表、凭据文件或 USB 接口。Ctrl-C 停止。地址变化时需重新检查令牌原点限制；不假定 `.local` 或私网 IP 已获 Apple 支持保证。

## 使用与验收

1. 不输入令牌时记录已知 WGS84 手工坐标，检查 JSON 中 `inputCRS` 为 `WGS84`，归一化值相同。空值、非有限值和超范围输入不能产生新记录。
2. 在页面输入仅供浏览器使用的 Maps token，点“加载 Apple 地图”。不要输入签名私钥。令牌仅保存在当前页面内存，不写 URL、浏览器存储、报告或 Mac 服务日志；刷新页面即可重新输入。所加载的 Apple SDK 会使用令牌访问 Apple 服务。
3. 检查底图实际可见，再点击人工观察按钮。SDK 初始化、底图可见、搜索完成分别记录，均不表示 USB 位置采用。
4. 搜索已知地点并选择结果，再在地图上点选同一地点。每次记录包含输入坐标、提供方、方法、时间；MapKit 的 `inputCRS` 为 `unverified-mapkit`，`normalizedWGS84` 为 `null`。
5. 为每个最新地图点填写独立 WGS84 参照及来源。至少覆盖搜索与点选、目标使用地区的多个已知点，并在现场执行前明确容差。记录参照不自动宣布校准通过，不执行猜测的 GCJ-02 转换。
6. 导出 JSON；包含坐标、地点、浏览器、访问原点，分享前自行核对。坐标是否可归一化的结论需结合实际对照记录评估；工具保持 `coordinateCalibration: unverified`。
7. 刷新后所有记录和令牌清空。过期令牌、错误原点、网络失败时检查失败提示和仍可用的手工输入。搜索和点选功能需要有效令牌，不能用离线检查代替验收。

## 验证记录

2026-10-29，通过本机浏览器交互验证：无令牌下手工 WGS84 记录、导出结构中的未验收标记、缺少令牌提示。开发采用先观察缺失行为、再实现并复测的浏览器流程。

可重复的浏览器用例位于 `tests/browser/maps-validation.mjs`。已有 Playwright 和 Chrome 的环境可在服务运行后执行：

```sh
node tests/browser/maps-validation.mjs
```

测试依赖可安装在仓库外；通过 `PLAYWRIGHT_MODULE` 指向 Playwright 的 `index.mjs`，通过 `MAPS_VALIDATION_URL` 指定工具地址。测试不使用真实令牌，不代表 Apple 服务或 iPhone 实测通过。

## 官方接口依据

2026-10-29 核对：

- [MapKit JS 加载方式](https://developer.apple.com/documentation/mapkitjs/loading-the-latest-version-of-mapkit-js)：工具按需加载主版本 6 的完整 bundle，减少验证入口的构建依赖；不是生产性能选型。
- [初始化事件](https://developer.apple.com/documentation/mapkitjs/handling-initialization-events)：区分初始化成功与错误，随后仍需人工观察底图。
- [搜索回调](https://developer.apple.com/documentation/mapkitjs/search/search1)：通过 error/data 与 places 处理搜索结果。
- [地图交互事件](https://developer.apple.com/documentation/mapkitjs/handling-map-events)和[页坐标转换](https://developer.apple.com/documentation/mapkitjs/map/convertpointonpagetocoordinate)：single-tap 的 pointOnPage 转为地图输入坐标。

这些接口依据不证明中国区域地图输入坐标已与 USB 后端 WGS84 校准。
