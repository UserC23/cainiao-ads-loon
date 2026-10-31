# cnads-loon

菜鸟 App（Cainiao 4iPhone）去广告 Loon 插件。

**v2 是 MITM 版**：拦截 MTop 广告位接口 + 改写页面响应体删除广告字段。
v1 的纯域名拦截方案实测无效，原因见 [docs/mitm-guide.md](docs/mitm-guide.md#一为什么-v1-完全没效果)。

- 适用 App 版本：`8.11.605`（抓包基线）
- 需要：开启 MITM + 安装并信任证书
- 覆盖：首页瀑布流、搜索栏广告词、接寄券、活动弹窗、飞猪广告位
- 详细说明：[docs/mitm-guide.md](docs/mitm-guide.md) ｜ 抓包分析：[docs/analysis.md](docs/analysis.md)

---

## 安装

### 1. 先开 MITM

Loon → 设置 → **MitM** → 打开
Loon → 设置 → **证书管理** → 生成并安装证书 → 到 iOS「设置 → 通用 → VPN与设备管理」**信任**它

> 不开 MITM、不信任证书，这个插件**一行都不会生效**。这是最常见的失效原因。

### 2. 添加插件

Loon → 配置 → 插件 → 右上角 `+` → 从 URL 添加：

```
https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin
```

### 3. 重启 App

菜鸟**上滑彻底杀掉**再重开，广告才会消失。App 有缓存，只切后台不杀进程无效。

### CDN 地址实测

| 地址 | 实测 |
|---|---|
| `https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://gcore.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://testingcf.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://ghproxy.net/https://raw.githubusercontent.com/UserC23/cnads-loon/main/CainiaoAds.plugin` | ✅ |
| `https://cdn.jsdelivr.net/gh/...` | ❌ 主域被污染 |
| `https://raw.githubusercontent.com/...` | ❌ 直连不通 |

jsDelivr 缓存约 12 小时。仓库更新后想立刻生效，把 `@main` 换成具体 commit SHA。

---

## 做了什么

### 广告位接口拦截（`reject-dict`）

| 接口 | 说明 |
|---|---|
| `mtop.cainiao.guoguo.nbnetflow.ads.*` | 广告位主接口：批量拉取 / 曝光回执 / 索引 |
| `mtop.cainiao.adx.flyad.getad` | 飞猪广告位 |
| `mtop.cainiao.adkeyword.get` | 搜索栏广告关键词 |
| `mtop.cainiao.nbopen.miniapp.recommend.cpc` | 小程序推荐位 CPC |
| `mtop.cainiao.nbmensa.research.researchservice.*` | 打断式调研弹窗 |
| `com.cainiao.cnactivitycenter` 等 | 营销/活动弹窗 |

用 `reject-dict` 返回 `{}` 而不是断连 —— App 解析成"无广告"，广告容器渲染为空，
不会白屏也不会报网络错误。

### 页面响应体改写（`http-response-jq`）

页面引擎接口（`mtop.cainiao.app.e2e.engine.page.fetch`）里，广告是跟正常内容混在
一个 JSON 里返回的。不能整包拒绝，只能定点删除：

```jq
del(.data.data.data.mainSearch.bizData.searchContents, .data.data.data.operationList)
```

### 域名级拦截（保留 v1）

1RTB、穿山甲/巨量、阿里妈妈 TanX、神马汇川，共 14 个域名。这些是第三方广告 SDK
的素材与上报链路，拦掉能减少下载和上报，但**不是广告内容的下发通道**。

## 故意没拦

| 域名 | 原因 |
|---|---|
| `amdc.m.taobao.com` | MTop 域名调度中心，不是广告。插件里给了按 UA 限定的可选拦截，默认关闭 |
| `ynuf.aliapp.org`、`fourier.taobao.com`、`fourier.alibaba.com` | 设备指纹，拦了有触发风控的风险 |

---

## 有残留广告怎么办

不保证你这个 App 版本全中，接口名会随版本变化。定位流程写在这里：
[docs/mitm-guide.md 第四节](docs/mitm-guide.md#四还有残留广告怎么定位)

一句话版本：开 Loon 请求日志 → 进有广告的页面 → 找响应体大的 `*-mtop.cainiao.com`
请求 → 看响应里的广告字段 → 补一条规则。

---

## 文件结构

```
CainiaoAds.plugin       Loon 插件（MITM 版，主文件）
rules/CainiaoAds.list   纯域名规则（辅助层，Surge/Shadowrocket/Stash 可用）
docs/mitm-guide.md      MITM 安装、验证、调优、排错
docs/analysis.md        抓包分析（285 条请求 / 68 调度域名）
tools/analyze_har.py    HAR 分析脚本
```

## 免责

规则整合自公开社区实践并结合本项目抓包分析整理，随 App 版本变化可能失效。
仅供个人学习自用，请自行评估风险。
