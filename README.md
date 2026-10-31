# cnads-loon

菜鸟 App（Cainiao 4iPhone）去广告 Loon 插件。

规则全部来自真机抓包分析，纯 `[Rule]` 域名级拦截，**不需要 MITM，不需要装证书**。

- App 版本：`8.11.605`
- 抓包：Loon HAR，285 条请求 / 68 个调度域名
- 拦截目标：1RTB、穿山甲/巨量引擎、阿里妈妈 TanX、神马汇川
- 详细分析：[docs/analysis.md](docs/analysis.md)

---

## 安装

### Loon

在 Loon 里依次进入 **配置 → 插件 → 右上角 + → 从 URL 添加**，粘贴：

```
https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin
```

添加后确认插件已启用即可，**不用开 MITM，也不用装证书**。

### 关于 CDN 地址

`cdn.jsdelivr.net` 主域和 `raw.githubusercontent.com` 在国内经常被污染或直连不通，
所以上面用的是 jsDelivr 的 **fastly** 子域。以下地址均已实测可通，可任选：

| 地址 | 实测 |
|---|---|
| `https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://gcore.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://testingcf.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin` | ✅ |
| `https://ghproxy.net/https://raw.githubusercontent.com/UserC23/cnads-loon/main/CainiaoAds.plugin` | ✅ |
| `https://cdn.jsdelivr.net/gh/...` | ❌ 主域被污染 |
| `https://raw.githubusercontent.com/...` | ❌ 直连不通 |

> jsDelivr 有缓存（约 12 小时）。仓库更新后想立刻生效，把地址里的 `@main`
> 换成具体的 commit SHA。

### 其他客户端

`rules/CainiaoAds.list` 是通用规则列表，Surge / Shadowrocket / Stash 可直接作为
remote rule 引用：

```
https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/rules/CainiaoAds.list
```

Quantumult X 需要改关键字（文件头有说明）：`DOMAIN-SUFFIX` → `HOST-SUFFIX`，
`DOMAIN` → `HOST`。

---

## 拦了什么

| 广告生态 | 域名 |
|---|---|
| 1RTB | `sdk.1rtb.net` |
| 穿山甲 / 巨量引擎 | `*.pglstatp-toutiao.com`、`pgdt.ugdtimg.com`、`p26-sign.douyinpic.com`、`*.ctobsnssdk.com` |
| 阿里妈妈 / TanX | `*.tanx.com`、`h-adashx.ut.cainiao.com`、`admonitor-feedback.cn-hangzhou.log.aliyuncs.com` |
| 神马 / UC | `huichuan-mc.sm.cn`、`image.uczzd.cn` |

## 故意没拦

这三类拦了得不偿失，插件里以注释形式写明了原因：

| 域名 | 原因 |
|---|---|
| `amdc.m.taobao.com` | 阿里 MTop **域名调度中心**，不是广告。本次抓包 281/285 条请求都打在这里，但它一旦被拦，App 大批业务域名解析失败 |
| `ynuf.aliapp.org`、`fourier.taobao.com`、`fourier.alibaba.com` | 设备指纹/风控链路。拦掉可能触发验证码、限流甚至降权 |
| `gm.mmstat.com` 等 | 统计埋点，不是广告。需要极致干净的可以手动打开注释 |

---

## 文件结构

```
CainiaoAds.plugin         Loon 插件（主文件）
rules/CainiaoAds.list     通用规则列表（Surge / Shadowrocket / Stash）
docs/analysis.md          抓包分析全过程与结论
tools/analyze_har.py      可复用的 HAR 分析脚本
```

## 自己补充规则

多抓几个页面（首页下滑、领券中心、签到页），导出 HAR 后跑：

```bash
python tools/analyze_har.py your.har --all      # 全貌
python tools/analyze_har.py your.har --ads      # 只看广告域名
```

`--ads` 会输出候选域名和规则草稿。**共享域要手动收窄**——比如
`admonitor-feedback.cn-hangzhou.log.aliyuncs.com` 必须用精确 `DOMAIN`，
写成 `log.aliyuncs.com` 后缀会连带干掉阿里云上所有业务日志。

---

## 已知局限

这份分析基于**一次**抓包、**一个**页面路径。菜鸟不同页面可能拉不同的广告位，
域名集合会比现在更大。另外抓包里 98% 的流量是调度噪音，真实广告请求只有 1 条
（1RTB，且返回空），所以本插件是「按 SDK 域名拦截」，不是「按实际广告响应拦截」。

如果装了之后某个广告位还在，大概率是它走了业务域的 MTop 接口下发内容。
那种情况只看域名是解不掉的，需要针对具体接口做 MITM 改写 —— 目前没有证据支撑，
不做猜测性拦截。

## 免责

仅供个人学习与自用，请自行评估使用风险。规则可能随 App 版本变化失效。
