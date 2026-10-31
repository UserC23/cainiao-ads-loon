# 变更记录

三个版本的原文都保留在仓库里，可随时回滚：

| 版本 | 文件 | 状态 |
|---|---|---|
| v3 | [`CainiaoAds.plugin`](CainiaoAds.plugin) | **当前版本**，建议安装 |
| v2 | [`archive/CainiaoAds-v2.plugin`](archive/CainiaoAds-v2.plugin) | 归档保留 |
| v1 | 仅存在于 git 提交 `7a3e35a` | 已被 v2 覆盖 |

---

## v3 — 2026-10-31

**一句话**：v2 在 Loon 里根本没被加载。v3 按 Loon 原生语法重写，并把规则从「锚定网关域名」改成「按路径匹配」。

### 修掉的三处错位

| # | v2 的写法 | 问题 | v3 的写法 |
|---|---|---|---|
| 1 | `[URL Rewrite]` / `[Body Rewrite]` | 这是 **Surge** 的段落名。Loon 只认 `[Rewrite]`，响应体改写用 `response-body-json-jq`。v2 的拦截规则一条都没进内存。 | `[Rewrite]` + `response-body-json-jq` |
| 2 | 规则写死 `cn-acs.m.cainiao.com`、`netflow-mtop.cainiao.com` | 菜鸟的 MTop 出口实际是 `guide-acs.m.taobao.com`，写死任何一个网关都会漏 | `^https?://[^/]+/gw/mtop\.…` 按路径匹配，网关是谁都行 |
| 3 | MITM hostname 逐个列了 17 个主机 | 漏了 `cnactivitycenter-mtop.cainiao.com` 等运行时才出现的主机 | `*.cainiao.com` 通配 + 3 个 taobao 网关 |

### 新增能力

- **「热门活动」模块**：按标题删除（`热门活动` / `活动中心` / `领券中心` / `福利中心` / `签到有礼`），不依赖字段路径
- **跳转淘宝的瀑布流广告卡片**：按 `cardType` / `bizType` / `itemType` = `ad` 判定，另加 `adInfo` / `adZoneId` / `cpcInfo` 这类广告专有字段兜底
- **开屏兜底**：`.splash` / `.startup` / `.launch` / `.advertise` 路径统一 reject-dict
- **活动中心接口**：`cnactivitycenter`（v2 只在路径里匹配，漏了主机名在前的情况）

### 结构改进

- 三条清洗规则合并成**一条 jq 表达式**。Loon 只有 3.2.3+ 才会把同正则的多条 rewrite 串行执行，合并后不依赖版本行为
- 所有 jq 表达式与正则都用真实 jq 引擎跑过用例验证，不是照文档抄的

### 安装方式变更：弃用 `@main`

实测本仓库的 `@main` 被 jsDelivr 卡在**最早的 v1（5710B）**，强推后各节点仍返回旧文件，
`purge.jsdelivr.net` 清了也不生效（强推可能没触发它的刷新）。

这意味着：**用 `@main` 安装的用户，装上的其实一直是 v1。**
"换了新版本却没变化"可能根本不是插件的问题，而是根本没换成功。

从此 README 只给固定 commit SHA 地址（内容寻址，不可变）。

---

## v2 — 2026-10-31

**一句话**：从「纯域名拦截」转向「MITM + 响应体改写」。

- 引入 `[MITM]`、A/B/C 三级 `reject-dict`、`[Body Rewrite]`
- 保留 v1 的域名级规则作为辅助层
- 新增 `docs/mitm-guide.md`

**实测结果**：开屏广告消失（由 v1 的域名规则干掉），首页瀑布流广告与「热门活动」全部还在。
原因见 v3 表格 —— 规则没被加载 + 网关锚错 + MITM 未覆盖。

---

## v1 — 2026-10-31

**一句话**：纯 `[Rule]` 域名拦截。

- 拦 1RTB、穿山甲/巨量、阿里妈妈 TanX、神马汇川，共 14 个域名
- **实测完全无效**：这些是第三方广告 SDK 的素材链路，广告内容本身由业务 MTop 接口下发，域名层永远碰不到

> v1 的判断失误在于把「广告 SDK 存在」当成了「广告内容从这里来」。
> 抓包里那些 SDK 域名确实有调度记录，但真正的下发通道是自家 MTop 网关。
