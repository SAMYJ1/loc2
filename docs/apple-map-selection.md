# 手机 Apple 地图选点

手机控制页现在可按需加载 Apple 地图、搜索地点和点选地图。任何地图操作只修改选点草稿，点击“应用位置”才改变目标。缺少令牌、加载失败、搜索失败时继续提供明确的 WGS84 手工输入。

## 本机配置

在私有 `~/.config/loc2/config.json` 中增加 `maps`，与现有 `runtime` 和 `phone` 配置并列；修改后重新打开 Mac 应用：

```json
{
  "maps": {
    "token": "<仅供页面使用的受限Maps令牌>",
    "coordinatePolicy": "unverified"
  }
}
```

页面令牌通过 **已授权** 的 `GET /api/maps-config` 发送到该控制端，仅在页面内存使用，不置于 URL 或浏览器存储。签名私钥留在本机，不能作为 token；其他本机配置字段不会由该接口返回。服务只接收 JWT 形状的页面令牌，失效/错误的令牌最终由 Apple 验证。局域网入口和令牌原点限制必须在实际 Safari 上验证，工具不会自动注册或付费购买地图服务。

`coordinatePolicy: unverified` 是默认值。地图来源草稿保留：

- `provider: apple-mapkit-js`
- `selectionMethod: search` 或 `map-tap`
- 原始 `inputCoordinate` 和显示坐标
- `inputCRS: unverified-mapkit`
- `normalizedWGS84: null`

此类草稿可以观察、保存，但界面禁用应用，服务也拒绝应用；不会把地图坐标填进标为 WGS84 的手工输入框。即使调用方伪造 WGS84 标记，只要本机策略未确认，服务仍拒绝地图来源。

## 现场校准后启用

先使用独立地图验证工具，完成同一实际入口、目标使用地区的搜索/点选与已知 WGS84 点对照，并保留环境、日期、参照来源、容差及结论。只有实测确认输入坐标无需转换即可作为 WGS84 时，才在本机改为：

```json
{
  "maps": {
    "token": "<页面令牌>",
    "coordinatePolicy": "validated-wgs84",
    "validationEvidence": "<真实校准报告的引用>"
  }
}
```

两项策略字段必须同时存在；空报告引用不会启用。配置是用户对已有证据的声明，软件不会替代审阅报告，也不会自动认定校准成立。当前尚无真实令牌及校准证据，不应填入示例占位值启用。

启用后重新选点，草稿标注 WGS84，归一化坐标与输入保持相同。服务再次验证本机策略、来源、参考系及输入/归一化/供数目标的一致性。早先保存的未校准草稿仍拒绝应用，需要重新选择。若实测发现坐标偏差，保持未校准状态；本版没有隐式 GCJ-02 转换。

## 浏览器安全策略

MapKit 按需加载主版本 6 的官方 bundle。CSP 仅增加 Apple 的地图 CDN、地图资源域、blob worker，并给 SDK 传递每次页面响应的随机 nonce。WebAssembly 使用 `wasm-unsafe-eval`，没有开启通用 `unsafe-eval` 或 `unsafe-inline`；其他页面脚本仍为同源。

依据 [Apple 的加载与 CSP 说明](https://developer.apple.com/documentation/mapkitjs/loading-the-latest-version-of-mapkit-js)，完整地图渲染需要 WebAssembly、worker/blob 和地图域的资源；nonce 用于 SDK 注入的脚本/样式。相关 API 依据另见独立地图验证工具文档。

## 验证边界

```sh
python3 -m unittest discover -s tests
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node tests/browser/apple-maps.mjs
```

HTTP 测试验证地图配置只向授权端提供、额外本机字段不泄漏、默认拒绝地图应用、显式本机策略及一致坐标才接受、手工输入仍可用。

浏览器测试使用明确标记的 **合成 SDK 与 USB 替身**，覆盖无令牌、未知参考系禁用应用、配置策略后的明确应用、搜索和点选只更新草稿、SDK 加载失败回退。它们证明应用边界行为，不证明 Apple 真实授权、地图底图、Safari 可达性或地区坐标已校准。上述现场项目统一留在 #9 验收。
