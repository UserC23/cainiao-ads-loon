# cainiao-ads-loon

菜鸟 App（Cainiao 4iPhone）去广告 Loon 插件。

- 适用 App 版本：`8.11.605`（抓包基线）
- 需要：**开启 MITM + 安装证书 + 在「证书信任设置」里开启完全信任**
- 当前版本：**v3**（历史版本见 [CHANGELOG.md](CHANGELOG.md)，v2 原文保留在 [`archive/`](archive/)）
- 详细说明：[docs/mitm-guide.md](docs/mitm-guide.md) ｜ 抓包分析：[docs/analysis-v3-har.md](docs/analysis-v3-har.md)

---

## 安装

### 1. 先开 MITM（这步不做，插件一行都不执行）

Loon → 设置 → **MitM** → 打开开关
Loon → 设置 → **证书管理** → 生成并安装证书
→ 系统「设置 → 通用 → VPN与设备管理」安装描述文件
→ **系统「设置 → 通用 → 关于本机 → 证书信任设置」打开 Loon 证书的完全信任**

> 最后一步最容易漏。只在「VPN与设备管理」里看到证书**不算信任**。

### 2. 删掉旧版插件，再添加 v3

先删除已安装的 v1/v2（两套规则会打架），然后 Loon → 配置 → 插件 → 右上角 `+` → 从 URL 添加：

```
https://fastly.jsdelivr.net/gh/UserC23/cainiao-ads-loon@36871d7ca03f3b8cd2fb69e9167e071c4d7e48df/CainiaoAds.plugin
```

> **建议用上面这个固定 commit 地址。**
> 仓库原名 `cnads-loon`，2026-10-31 改名为 `cainiao-ads-loon`。
> 改名后新路径的 `@main` 能用了，但实测**推完仍返回上一个提交**（会滞后），
> 旧仓库名下的 `@main` 更是长期卡在 v1（5710B），`purge.jsdelivr.net` 都清不掉。
> 分支缓存不可靠，固定 SHA 地址是内容寻址的，永远拿到确切版本。
>
> **已安装过旧插件的话，要重新添加一次这个新地址**：
> 仓库改名后 jsDelivr 的旧路径（`/gh/UserC23/cnads-loon/...`）不再提供文件。

### 3. 重启 App

菜鸟**上滑彻底杀掉**再重开。只切后台无效，页面 JSON 有缓存。

---

## 做了什么

| 层 | 手段 | 作用对象 | 默认 |
|---|---|---|---|
| A | `reject-dict` | 广告位接口：`nbnetflow.ads.*`、`adx.flyad.getad`、`adkeyword`、小程序推荐 CPC、开屏/启动 | ✅ |
| B | `reject-dict` | 活动中心 `cnactivitycenter`、龙泉运营位、tabbar 营销 | ✅ |
| C | `reject-dict` | 主流程接口（`homepage.merge` 等，会让页面空白） | ❌ |
| 响应体 | `response-body-json-jq` | 页面 JSON 里的「热门活动」模块、广告卡片、搜索框广告词 | ✅ |
| 域名 | `[Rule]` | 1RTB、穿山甲/巨量、TanX、神马汇川（14 个域名） | ✅ |

`reject-dict` 返回 HTTP 200 + `{}`，App 解析成「这次没广告」，容器渲染为空，不会白屏也不会报网络错误。

### 页面 JSON 清洗

广告和正常内容是混在同一个 JSON 里返回的，不能整包拒绝，只能定点删。v3 的核心规则是一条 jq 表达式：

```jq
del(.. | select(type == "object" and (...title 匹配 热门活动/活动中心/领券中心...)))
| del(.. | select(type == "object" and (has("adInfo") or has("adZoneId") or has("cpcInfo") ...)))
| del(.. | select(type == "object" and (...cardType/bizType = ad...)))
```

## v3 修掉了 v2 的三处错位

v2 "装了跟没装一样"不是规则不够多，是根本没被执行：

| # | 问题 | v3 |
|---|---|---|
| 1 | 用了 Surge 段落名 `[URL Rewrite]` / `[Body Rewrite]`，Loon 只认 `[Rewrite]` + `response-body-json-jq` | 全部改成 Loon 原生语法 |
| 2 | 规则锚死 `cn-acs.m.cainiao.com`，实际网关是 `guide-acs.m.taobao.com` | 改成 `^https?://[^/]+/gw/mtop\.…` 按路径匹配 |
| 3 | MITM 主机逐个列了 17 个，漏 `cnactivitycenter-mtop` 等 | `*.cainiao.com` 通配 + 3 个淘宝网关 |

细节见 [CHANGELOG.md](CHANGELOG.md)。

---

## 版本归档

| 版本 | 文件 | 说明 |
|---|---|---|
| v3 | [`CainiaoAds.plugin`](CainiaoAds.plugin) | 当前版本 |
| v2 | [`archive/CainiaoAds-v2.plugin`](archive/CainiaoAds-v2.plugin) | 原文保留，可回滚 |
| v1 | git 提交 `7a3e35a` | 纯域名版，已被覆盖 |

回滚到 v2 的话，用 `archive/CainiaoAds-v2.plugin` 的固定 commit 地址安装，并先卸载 v3。
注意 v2 在 Loon 里不会生效（段落名问题），仅作留档。

---

## 有残留广告怎么办

别猜字段，用脚本定位：

```bash
python tools/analyze_har.py 抓包.har --check      # 先确认 MITM 真的在解密
python tools/analyze_har.py 抓包.har --scan-ads   # 直接输出广告字段路径
```

`--check` 是前置条件：如果输出 `❌ 没有任何 HTTPS 请求`，说明 MITM 没生效，
此时任何分析都没有意义 —— 插件里的 `[Rewrite]` 一条都不会执行。

详细流程见 [docs/mitm-guide.md 第四节](docs/mitm-guide.md#四还有广告怎么办)。

---

## CDN 地址实测

| 地址 | 实测 |
|---|---|
| `fastly.jsdelivr.net/gh/UserC23/cainiao-ads-loon@<commit-sha>/CainiaoAds.plugin` | ✅ 推荐，内容寻址 |
| `gcore.jsdelivr.net/gh/UserC23/cainiao-ads-loon@<commit-sha>/CainiaoAds.plugin` | ✅ |
| `testingcf.jsdelivr.net/gh/UserC23/cainiao-ads-loon@<commit-sha>/CainiaoAds.plugin` | ✅ |
| `.../cainiao-ads-loon@main/CainiaoAds.plugin` | ⚠️ 能取到，但会滞后一个提交 |
| `ghproxy.net/https://raw.githubusercontent.com/UserC23/cainiao-ads-loon/main/CainiaoAds.plugin` | ✅ 实时，但依赖第三方代理 |
| `.../cnads-loon@main/...`（旧仓库名） | ❌ 缓存卡在 v1（5710B），已随改名废弃 |
| `cdn.jsdelivr.net/gh/...` | ❌ 主域被污染 |
| `raw.githubusercontent.com/...` | ❌ 直连不通 |

---

## 文件结构

```
CainiaoAds.plugin             Loon 插件 v3（主文件，直接装这个）
archive/CainiaoAds-v2.plugin  v2 原文留档
rules/CainiaoAds.list         纯域名规则（Surge/Shadowrocket/Stash 可用，不含 MITM 部分）
docs/mitm-guide.md            安装、验证、定位残留广告、排错
docs/analysis.md              v1 抓包分析（285 条 / 68 调度域名）
docs/analysis-v3-har.md       v2 安装后抓包分析（证明 MITM 未生效）
tools/analyze_har.py          HAR 分析脚本（--check / --scan-ads / --dispatch）
CHANGELOG.md                  三个版本的问题与修正
```

## 免责

规则整合自公开社区实践并结合本项目抓包分析整理，随 App 版本变化可能失效。
仅供个人学习自用，请自行评估风险。
