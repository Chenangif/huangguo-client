# 站点结构说明（逆向整理）

> 记录 huangguoai.com 的页面与接口结构，供两端解析层共用。站点改版时需同步更新。

## 1. 列表数据

### 分类 JSON 接口（推荐，分页准确）
```
GET /api/videos/category/{category}?page=N&size=21
```
返回：
```json
{
  "data": {
    "items": [ { "id": "...", "title": "...", "coverSrc": "...", ... } ],
    "pagination": { "page": 1, "pages": 12, "total": 245 }
  }
}
```
分类 slug：`ai-duanju` / `ai-manju` / `ai-huanlian` / `ai-mogai`。

请求必须带 `User-Agent`，建议同时带 `Referer: https://huangguoai.com/`。

### HTML 卡片（首页 / 搜索 / 排行榜）
- 卡片容器：`class` 含 `hg-drama-card`
- 链接：`href="/video/{id}/"`（**早期第三方文档写的 `/detail/{id}/` 已失效**）
- 封面：在 `data-src` 属性里（`src` 常为占位图），域名 `pic.wirqed.cn`，带 `auth_key` 签名参数

兜底解析（不依赖类名）：直接正则抓 `/video/(\d+)/` 链接 + 就近取 `alt` 与图片地址。

## 2. 详情页

```
GET /video/{id}/          # 第一集
GET /video/{id}/ep-{n}/   # 第 n 集
```

- 选集条目：`.hg-web-play__ep`，含 `href="/video/{id}/ep-{n}/"` 与 `data-ep-id`
- 元数据：页内 `<script id="videoInitialData" type="application/json">`，字段：
  `title` / `description` / `coverSrc` / `videoSrc` / `tags` / `epPlaySrcs`

## 3. 封面解密

封面字节为 **AES-128-CBC** 加密：
- key：`f5d965df75336270`（**16 字节 UTF-8 字符串**，不是 8 字节 hex 解码）
- iv：`97b60394abc2fbe1`（同上）
- PKCS7 填充；解密后是标准 JPEG/PNG

若某张图解密后不是有效图片头，回退用原始字节。

## 4. 播放链路

- `videoSrc` 是 m3u8 地址（可能是 master playlist，需选最高码率子列表）
- 请求 m3u8 与分片只需带 `User-Agent`（多数情况 Referer 非必需，但带上更稳）
- 若含 `#EXT-X-KEY:METHOD=AES-128`：
  - 有 `IV=` → 用该十六进制 IV
  - 无 `IV=` → **隐式 IV**，取该分片的 media sequence，写成 16 字节大端整数
- 桌面端通过**本地代理**（127.0.0.1 随机端口）把 m3u8 内的分片/密钥 URI 全部重写指回代理，由代理带站点头转发，从而让 hls.js 正常播放。

---

## 已知坑

| 现象 | 原因 / 处理 |
|---|---|
| 列表解析为 0 条 | 站点已改为 `/video/{id}/`，旧的 `/detail/{id}/` 规则失效 |
| 海报全黑/损坏 | key 要用 16 字节 UTF-8 字符串，不是 hex 解码后的 8 字节 |
| 手机端加载失败 | 原生客户端的 TLS 指纹可能被拦；已用 OkHttp（MODERN+COMPATIBLE TLS）+ 宽松证书重试 + WebView 兜底三层处理 |
| m3u8 播放花屏 | 无 `IV=` 时漏了隐式 IV（media sequence 大端） |
