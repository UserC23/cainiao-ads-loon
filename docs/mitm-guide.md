# MITM 版插件使用与调优指南

## 一、为什么 v1 完全没效果

v1 是纯 `[Rule]` 域名拦截，拦的是 1RTB、穿山甲、阿里妈妈这些**独立广告域名**。
问题在于：菜鸟的广告**不是从这些域名下发的**。

真实链路是这样：

```
App 启动
  └─ 请求业务 MTop 网关（cn-acs.m.cainiao.com 等）
       └─ 网关返回一整个页面 JSON
            └─ 广告位作为 JSON 里的某个字段被一起带回来
                 └─ App 把这个字段渲染成 banner / 瀑布流卡片 / 弹窗
```

广告内容藏在**业务响应体**里，域名是正常的 `*-mtop.cainiao.com`。
域名层拦截永远碰不到它，所以装了跟没装一样 —— 这是 v1 判断失误的地方。

顺带一提，v1 拦的那些 SDK 域名（穿山甲素材包、1RTB 等）确实存在，抓包里也有调度记录，
但它们更接近「第三方广告 SDK 的备胎链路」。主链路还是走自家 MTop。

---

## 二、v2 的三层策略

| 层级 | 手段 | 作用对象 | 默认 |
|---|---|---|---|
| A 级 | `reject-dict` | 明确的广告位接口（`...nbnetflow.ads.*`、`adx.flyad.getad`、`adkeyword.get`） | ✅ 开 |
| B 级 | `reject-dict` | 活动/营销弹窗接口 | ✅ 开 |
| C 级 | `reject-dict` | 主流程接口（homepage.merge、nbcps.presentation.fetch） | ❌ 关 |
| Body | `http-response-jq` | 页面 JSON 里塞的广告字段，定点 `del()` | ✅ 开 |

### 为什么用 `reject-dict` 而不是 `REJECT`

`REJECT` 会把连接直接断掉，App 拿到的是网络错误，很多 SDK 会走「失败重试」分支，
反而更卡；而且 MTop 层可能会弹「网络异常」提示。

`reject-dict` 返回的是 HTTP 200 + `{}`。App 解析出来是「空数据」，
广告容器渲染为空，等同「这次没有广告」。这是社区通用的稳做法。

### 为什么主流程接口默认关闭

`homepage.merge`、`nbcps.presentation.fetch` 这类接口名字里没有 ad，
但它们**同时承载正常内容**。整包 reject 的后果是首页可能直接空白。

如果你能接受「首页变成只剩基础模块」换取更干净，可以打开 C 级。
不能接受，就保持关闭，靠 `[Body Rewrite]` 定点删字段 —— 那个是安全的。

---

## 三、安装步骤（缺一步都不生效）

1. **Loon → 设置 → MitM → 打开**
2. **Loon → 设置 → 证书管理 → 生成/安装证书** → 跳到系统「设置 → 通用 → VPN与设备管理」**信任**该证书
3. **Loon → 配置 → 插件 → + → 从 URL 添加**：
   ```
   https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@main/CainiaoAds.plugin
   ```
4. 确认插件开关为**启用**
5. **菜鸟 App 彻底上滑杀掉，重新打开**

### 怎么确认 MITM 真的生效了

- Loon → 首页 → 打开**请求日志**，重新进菜鸟首页，看有没有 `cn-acs.m.cainiao.com` 的请求出现
- 如果日志里这些请求显示为 `REJECT` / 空响应 → MITM 生效了
- 如果完全看不到 `cainiao.com` 的请求 → MITM 没开或证书没信任

这一步不确认，后面调什么都是盲调。

---

## 四、还有残留广告怎么定位

v2 的规则来自社区公开的菜鸟去广告实践，覆盖了主要广告位，但**不能保证你这个版本全中**。
App 版本一改，接口名就可能变。

定位方法：

1. 保持 Loon 请求日志开着，进入有广告的那个页面
2. 在日志里找**响应体比较大**的 `*-mtop.cainiao.com` 请求（广告位 JSON 通常几 KB 到几十 KB）
3. 点开看响应，搜 `ad` / `banner` / `itemType` 之类字段
4. 找到之后，按下面两种方式处理：

**整个接口都是广告** → 加一条 URL Rewrite：
```
^https://该域名/gw/该接口名 reject-dict
```

**接口里混着正常内容** → 加一条 Body Rewrite，只删广告字段：
```
http-response-jq ^https://该域名/gw/该接口名 'del(.路径.到.广告字段)'
```

如果字段路径不好确定，直接用插件里那条被注释的**通用清洗**规则，
按字段名递归删（它的正则命中 `ads`/`adList`/`adItem` 这类键名就删）。

---

## 五、抓包是最终手段

如果日志看着太累，直接抓包。在广告出现的页面抓一段，导出 HAR 后跑：

```bash
python tools/analyze_har.py 你的抓包.har --hosts   # 看有哪些 mtop 接口
```

然后手动翻响应体大的那几条，广告就在里面。

> 注意：`analyze_har.py --ads` 是按**广告域名**找的，对 MTop 内嵌广告无效。
> 找内嵌广告要看 `--hosts` 再人工翻响应体。

---

## 六、可能踩的坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 完全不生效 | MITM 没开 / 证书没信任 | 按第三节逐条检查 |
| 首页空白或报错 | 开了 C 级规则 | 注释掉 C 级 |
| 领券失败 | B 级 `cnactivitycenter` 被拦 | 注释掉那一条 |
| 提示网络异常 | 某接口被 reject 但 App 不认空 JSON | 把该条 `reject-dict` 换成 `[Body Rewrite]` 定点删 |
| 改完没反应 | jsDelivr 缓存（约 12h） | 地址 `@main` 换成具体 commit SHA |
| 部分广告还在 | 走了未覆盖的接口 | 按第四节定位后补规则 |

---

## 七、声明

规则整合自公开的社区实践（Stash/Loon 菜鸟去广告模块）并结合本项目抓包分析整理，
不保证对所有 App 版本有效。仅供个人学习自用。
