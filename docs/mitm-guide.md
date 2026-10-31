# 使用与调优指南（v3）

> 版本演进和每版为什么失效，见 [CHANGELOG.md](../CHANGELOG.md)。
> 本次抓包的逐条分析，见 [analysis-v3-har.md](analysis-v3-har.md)。

---

## 零、先确认 MITM 真的在工作

这一步不做，后面全是白费。**v2 就是死在这里**。

Loon → 设置 → **MitM**：

1. 打开 **MitM 开关**
2. **证书管理 → 生成证书 → 安装**，跟随系统提示装好描述文件
3. 装完后**必须**再去这里打开开关：
   **设置 → 通用 → 关于本机 → 证书信任设置 → 找到 Loon 的证书 → 打开「启用完全信任」**

> 第 3 步是绝大多数人漏掉的一步。只在「VPN与设备管理」里看到证书**不算信任**，
> 必须在「证书信任设置」里打开开关，Loon 才能解密 HTTPS。

### 怎么验证（30 秒）

打开 Loon 首页的**请求日志**，然后：

- 进菜鸟首页 → 日志里应该出现 `https://guide-acs.m.taobao.com/...` 或 `https://cn-acs.m.cainiao.com/...` 的**完整 URL**，点开能看到响应体
- 如果只显示 `CONNECT`、或者压根看不到 cainiao 的请求 → MITM 没生效，回去做第 3 步

已经抓了包的话，可以直接用脚本判：

```bash
python tools/analyze_har.py 你的抓包.har --check
```

- 输出 `❌ 没有任何 HTTPS 请求` → MITM 没解密，插件一行都没跑
- 输出 `✅ 解密正常` → 继续往下

---

## 一、v3 相比 v2 改了什么

v2 装了没效果的真正原因有三条，都不是"规则写得不够多"：

### 1. 段落名写成了 Surge 的

| v2 写的 | Loon 认的 |
|---|---|
| `[URL Rewrite]` | `[Rewrite]` |
| `[Body Rewrite]` + `http-response-jq` | `[Rewrite]` + `response-body-json-jq` |

Loon 只解析 `[Rewrite]`。v2 里那些 `reject-dict` 和 jq 规则**一条都没被加载**进内存。

### 2. 网关锚错了

v2 把规则写死成 `cn-acs.m.cainiao.com`、`netflow-mtop.cainiao.com`。但菜鸟的 MTop 请求实际打在 **`guide-acs.m.taobao.com`** 上。

v3 全部改成按路径匹配：

```
^https?://[^/]+/gw/mtop\.cainiao\.guoguo\.nbnetflow\.ads\. reject-dict
```

`[^/]+` 表示"哪个网关都行"。这样网关换域名也不用改规则。

### 3. MITM 主机列不全

v2 逐个列了 17 个主机，漏了 `cnactivitycenter-mtop.cainiao.com`（活动中心）这种运行时才出现的主机。

v3 用 `*.cainiao.com` 通配 + 三个淘宝网关。

---

## 二、v3 的规则结构

| 层 | 手段 | 打什么 | 默认 |
|---|---|---|---|
| A | `reject-dict` | 广告位接口（`nbnetflow.ads`、`adx.flyad`、`adkeyword`、小程序 CPC、开屏/启动） | ✅ |
| B | `reject-dict` | 活动中心（`cnactivitycenter`）、龙泉运营位、tabbar 营销 | ✅ |
| C | `reject-dict` | 主流程接口（`homepage.merge`、`nbcps.presentation.fetch`） | ❌ |
| Body | `response-body-json-jq` | 页面 JSON 里的热门活动模块、广告卡片、搜索框广告词 | ✅ |

### 为什么用 `reject-dict` 而不是 `REJECT`

`REJECT` 是直接断连，App 收到网络错误，很多 SDK 会走重试分支，还可能弹"网络异常"。

`reject-dict` 返回 HTTP 200 + `{}`。App 解析成"这次没广告"，容器渲染为空。这是最稳的。

### 三条清洗规则为什么合成一条

核心清洗做了三件事（删热门活动类模块、删带广告字段的对象、删标记为 ad 的卡片）。

Loon 只有 **3.2.3 以上**才会把「同一正则的多条 rewrite」按顺序串行执行，版本低一点只跑第一条。所以 v3 把它们合并成一条 jq 表达式：

```jq
del(.. | select(...)) | del(.. | select(...)) | del(.. | select(...))
```

单条表达式，任何 Loon 版本行为一致。

### 为什么主流程接口默认关闭

`homepage.merge`、`nbcps.presentation.fetch` 这些接口名字里没有 ad，但**同时承载正常内容**。整包 reject 的后果是首页直接空白。

想更干净可以打开 C 级，但要接受白页。

---

## 三、安装

1. **先删掉已安装的旧版本**（v1/v2），两套规则同时存在会互相打架
2. 确认零、里的 MITM 三步都做了
3. Loon → 配置 → 插件 → 右上角 `+` → 从 URL 添加：

```
https://fastly.jsdelivr.net/gh/UserC23/cnads-loon@69b3ac2a41f2de556fd319da0162a3a0ab747d15/CainiaoAds.plugin
```

4. 确认插件开关为**启用**
5. 菜鸟 App **上滑彻底杀掉**，重新打开（只切后台无效，页面有缓存）

> **别用 `@main`。**
> 本仓库的 `@main` 被 jsDelivr 缓存卡在最早的 v1（5710B），强推不刷新、
> `purge.jsdelivr.net` 也清不掉。用 `@main` 装到的会是 v1 ——
> 这正是"换了新版本却毫无变化"的隐藏原因之一。
> 上面的固定 SHA 地址是内容寻址的，永远拿到确切版本。

---

## 四、还有广告怎么办

先别猜，用脚本定位。

### 1. 抓一段有效抓包

前提：`--check` 能过。抓的时候：

- 清空 Loon 日志 → 杀进程重开菜鸟
- 在**有广告的那个页面**停留 15~30 秒，瀑布流滑到底
- 导出 HAR

### 2. 定位字段

```bash
python tools/analyze_har.py 抓包.har --check      # 确认 MITM 生效
python tools/analyze_har.py 抓包.har --scan-ads   # 直接输出广告字段路径
```

输出长这样：

```
--- guide-acs.m.taobao.com/gw/mtop.cainiao.app.e2e.engine.page.fetch/1.0/
    $.data.data.modules[0].title      ← 标题 = 热门活动
    $.data.data.modules[2].cardType   ← 卡片类型 = ad
    $.data.data.modules[3].adInfo     ← 广告字段名 adInfo
```

### 3. 补规则

**整个接口都是广告** → URL Rewrite：

```
^https?://[^/]+/gw/mtop\.cainiao\.你的接口名 reject-dict
```

**接口里混着正常内容** → Body Rewrite，只删字段：

```
^https?://[^/]+/gw/mtop\.cainiao\.你的接口名 response-body-json-jq 'del(.data.data.modules[3])'
```

路径把脚本输出的 `$.` 去掉即可：`$.data.data.modules[3]` → `.data.data.modules[3]`。

如果字段名拿不准，打开插件里「高级 B」那条按字段名全量清洗的规则救急。

---

## 五、排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| 一点变化都没有 | 段落名/语法不被 Loon 识别，或 MITM 没生效 | 跑 `--check`；确认插件是 v3 |
| 开屏没了但首页广告还在 | MITM 没解密，只有域名规则在起作用 | 零、第 3 步「证书信任设置」 |
| 首页空白 | 开了 C 级规则 | 注释掉 C 级 |
| 我的页空了一块 | 热门活动模块被删，容器留白 | 正常现象；想恢复就注释核心清洗 |
| 签到/领券失效 | B 级 `cnactivitycenter` 被拦 | 注释掉 B 级那两条 |
| 提示网络异常 | 某个接口拒绝空 JSON | 把该条 `reject-dict` 改成 Body Rewrite 定点删 |
| 改完没反应 | jsDelivr 缓存 | 地址 `@main` 换成具体 commit SHA |
| 淘宝/其他 App 变卡 | MITM 解密了 `guide-acs.m.taobao.com` 的公共流量 | 关掉 MITM 总开关，或改用 `rules/CainiaoAds.list` 纯域名方案 |

---

## 六、声明

规则整合自公开社区实践（Loon/Stash 菜鸟去广告模块）并结合本项目抓包分析整理，
不保证对所有 App 版本有效。App 升级后接口名可能变，用第四节的流程重新定位即可。

仅供个人学习自用。
