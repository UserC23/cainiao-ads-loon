# 抓包分析（v2 安装后 / `294_1793437267246.har`）

这份抓包是装上 v2 插件之后录的，用来定位「开屏没了、首页瀑布流和热门活动还在」的原因。

结论先说：**这份抓包里没有任何一条能被规则命中的请求**，因为它压根没被解密。

---

## 一、数据概况

| 项目 | 值 |
|---|---|
| 采集工具 | Loon（HAR 1.0） |
| 条目数 | 101 |
| 时间窗 | 2026-10-31 17:01:09 → 17:02:28（约 80 秒） |
| 域名 | 3 个 |
| 协议 | **101 条全是 `http://`，0 条 `https://`** |

域名分布：

| 条数 | 域名 | 性质 |
|---|---|---|
| 99 | `amdc.m.taobao.com` | MTop 域名调度中心 |
| 1 | `atoken.m.taobao.com` | 登录 token，403 |
| 1 | `119.29.29.98` | DNS 探测 |

---

## 二、为什么说 MITM 没生效

这是整份分析里最有价值的一条证据：

> **101 条请求全是明文 `http://`。**

Loon 的 HAR 只记录它**看得到完整内容**的请求。HTTPS 请求一旦被 MITM 解密，请求会以 `https://` 出现在 HAR 里，并且能看到响应体；没被解密的 HTTPS 请求根本不会作为条目出现（只有 CONNECT 隧道，导出 HAR 时被过滤掉）。

所以「0 条 https」只有一种解释：**这一轮里没有任何 HTTPS 请求被解密**。

菜鸟 App 的业务接口全部走 HTTPS（`guide-acs.m.taobao.com`、`cn-acs.m.cainiao.com` 等）。它们连"出现"都没出现，说明：

- `[MITM]` 的 hostname 覆盖不到它们，或者
- Loon 的 MITM 总开关没开，或者
- 证书装了但没在「证书信任设置」里开启完全信任

无论哪一种，**插件的 `[Rewrite]` 一条都不会执行**。

### 那开屏广告为什么没了

v2 里保留了 v1 的 `[Rule]` 域名拦截（1RTB / 穿山甲 / TanX / 神马汇川）。域名规则走的是 DNS/连接层，**不需要 MITM**。

开屏广告正好由这些第三方 SDK 拉取，所以被域名规则干掉了。而首页瀑布流广告和「热门活动」是业务接口返回的 JSON 字段，必须 MITM 才能碰 —— 于是原样保留。

这刚好解释了「一部分没了、一部分还在」的割裂现象。

---

## 三、调度数据里的一条线索

99 条 amdc 请求解码后，涉及 35 个域名。其中一条值得注意：

```
cnactivitycenter-mtop.cainiao.com
```

这是**活动中心**的 MTop 主机。v2 的 `[MITM]` 列表里逐个列了 17 个主机，但**没有这一个** —— v2 的规则全都锚定在 `cn-acs.m.cainiao.com`、`netflow-mtop.cainiao.com` 这些写死的主机上。

这就是「逐个列主机」这种写法的根本问题：主机名是运行时才确定的，列不全。

v3 改成 `*.cainiao.com` 通配，一并解决。

### 调度到的 35 个域名（节选）

| 域名 | 次数 | 归类 |
|---|---|---|
| `gm.mmstat.com` | 31 | 统计（埋点） |
| `cainiao-app-logs.cn-zhangjiakou.log.aliyuncs.com` | 29 | 日志上报 |
| `admonitor-feedback.cn-hangzhou.log.aliyuncs.com` | 17 | 广告监控上报 |
| `huichuan-mc.sm.cn` | 13 | 神马/UC 广告 |
| `cn.alicdn.com` | 6 | 阿里 CDN |
| `nbnetflow-reply-log.cn-wulanchabu.log.aliyuncs.com` | 6 | 信息流日志 |
| `toblog.ctobsnssdk.com` | 5 | 穿山甲日志 |
| `h-adashx.ut.cainiao.com` | 4 | 阿里妈妈广告 |
| `fourier.alibaba.com` / `fourier.taobao.com` | 4 / 4 | 设备指纹（勿拦） |
| `df.tanx.com` | 3 | TanX 广告 |
| `image.uczzd.cn` | 2 | UC 广告素材 |
| `cnactivitycenter-mtop.cainiao.com` | 1 | **活动中心（v2 漏了）** |
| `item.taobao.com` / `detail.tmall.com` | 1 / 1 | 广告落地页 |

`item.taobao.com` 和 `detail.tmall.com` 出现在调度里，基本可以确认「首页那些能跳淘宝的卡片」的落地页形态 —— 但**不能按落地域名拦**，那是淘宝商品页，拦了正常商品也跳不过去。

---

## 四、这次抓包证明不了什么

必须说清楚：**这份数据没法用来确定广告 JSON 的字段名**。

因为没有任何一条业务响应被解密，看不到 `mtop.…page.fetch` 返回的 JSON 结构。所以 v3 里那三条 jq 清洗规则是基于：

1. 社区公开的菜鸟去广告实践（`nbnetflow.ads`、`adx.flyad`、`adkeyword` 等接口名）
2. 淘宝系 App 通用的卡片标记约定（`cardType` / `bizType` = `ad`，`adInfo` / `cpcInfo` 等）
3. 语义匹配（模块标题）

而不是「看着真实响应字段写的」。这点必须诚实。

---

## 五、下次抓包怎么抓才有用

按顺序做，缺一步这份抓包就白抓：

1. **先确认 MITM 真的在解密**
   打开 Loon 请求日志 → 进菜鸟首页 → 日志里必须能看到 `https://guide-acs.m.taobao.com/...` 或 `https://cn-acs.m.cainiao.com/...` 的完整 URL，并且能点开看响应体。
   只有 `CONNECT` 或什么都没有 → 别抓，先修 MITM。

2. **清空日志，回到菜鸟，杀掉进程重开**

3. **在广告出现的页面停留 15~30 秒**，把首页瀑布流滑到底，再进「我的」页

4. **导出 HAR**

5. 跑分析：

```bash
python tools/analyze_har.py 新抓包.har --check      # 先看 MITM 有没有生效
python tools/analyze_har.py 新抓包.har --scan-ads   # 直接定位广告字段路径
```

`--scan-ads` 会遍历所有 JSON 响应，把「像广告」的字段路径列出来（`cardType=ad`、`adInfo`、标题含「热门活动」等），
拿到路径后补一条 `response-body-json-jq` 即可，不用再猜。
