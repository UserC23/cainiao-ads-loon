# 菜鸟 App 抓包分析

数据来源：`293_1793435100507.har`（Loon 导出，HAR 1.0）

| 项目 | 值 |
|---|---|
| 抓包工具 | Loon 1.0 |
| 客户端 | `Cainiao4iPhone/55521970`，App 版本 `8.11.605` |
| 环境 | iPhone / iPhoneOS / WiFi |
| 请求总数 | 285 |
| 实际请求域名 | **3 个** |
| 调度域名 | 68 个 |

---

## 一、这 285 条请求的真实构成

| 域名 | 条数 | 性质 |
|---|---:|---|
| `amdc.m.taobao.com` | 281 | MTop 动态域名调度中心 |
| `atoken.m.taobao.com` | 3 | token 校验失败跳转的错误页（403） |
| `sdk.1rtb.net` | 1 | **1RTB 广告 SDK，本次唯一真实广告请求** |

响应状态：200 × 280、403 × 3、0 × 2（两条未完成，含那条 1RTB）。

也就是说：**这份抓包里 98% 的流量是「域名调度」的噪音，不是广告本身。**
真正的广告请求只有 1 条，而且是空的。想靠「抓了多少广告请求」来判断插件效果，
在这份数据上是不成立的——只能靠「广告 SDK 的域名是否被调起」来推断。

---

## 二、AMDC 是什么，为什么不能拦

`amdc.m.taobao.com/amdc/mobileDispatch` 是阿里的 **MTop 动态调度中心**（Alibaba Mobile
Dispatch Center）。它不是广告接口，而是一个「域名解析调度网关」：

- App 把要访问的域名打包成表单，base64 编码后 POST 上去
- 服务端返回一份 `dns` 数组，告诉 App 每个域名该走哪些 IP、什么协议、TTL 多久

### 解码方式（两层）

```
1. base64 解 postData  ->  "domain=xxx&sid=...&appName=Cainiao4iPhone&..."
2. 对第 1 层结果做 parse_qs  ->  取 domain 字段（空格分隔，可多个）
```

响应同样是 base64，解开是 JSON：

```json
{
  "code": 1000,
  "dns": [
    {
      "host": "gm.mmstat.com",
      "servers": [{
        "channels": [{
          "attributes": [{"port": 443, "protocol": "https"}],
          "ips": ["58.221.7.x", "..."]
        }]
      }],
      "ttl": 300,
      "um": 1
    }
  ],
  "ip": "223.153.49.191",
  "secData": "..."
}
```

`um` 字段值得注意：

- `um: 1` —— 有真实解析结果，返回 IP 列表与 https/http2/http3 通道
- `um: 3` —— `servers` 为空，**等于告诉 App「这个域名我不管，走本地 DNS」**

抓包里绝大多数域名都是 `um: 3`。也就是说这个调度器在这台设备上基本是个转发壳，
真正被它接管解析的只有 alicdn、mmstat、alipayobjects、部分 cainiao mtop 等少数域名。

**结论：不能拦 `amdc.m.taobao.com`。** 拦掉它，App 拿不到这批域名的调度结果，
业务请求会大面积失败。抓包里 281 条打在这儿只是调度噪音，不代表它是垃圾域名。

---

## 三、68 个调度域名分类

### 3.1 广告链路（13 个，插件拦截目标）

| 域名 | 次数 | 归属 | 说明 |
|---|---:|---|---|
| `admonitor-feedback.cn-hangzhou.log.aliyuncs.com` | 204 | 阿里妈妈 | 广告监测回传，**最高频**，纯上报 |
| `h-adashx.ut.cainiao.com` | 7 | 阿里妈妈 | 广告曝光/点击回传（adashx） |
| `df.tanx.com` | 6 | 阿里妈妈 TanX | 广告投放主域 |
| `sf3-fe-tos.pglstatp-toutiao.com` | 5 | 穿山甲 | 素材包 CDN |
| `p26-be-pack-sign.pglstatp-toutiao.com` | 5 | 穿山甲 | 素材包签名 |
| `pgdt.ugdtimg.com` | 5 | 巨量引擎 | 广告素材图床 |
| `toblog.ctobsnssdk.com` | 5 | 穿山甲 | SDK 日志上报 |
| `p26-sign.douyinpic.com` | 4 | 穿山甲 | 素材签名（抖音图床） |
| `p3-be-pack-sign.pglstatp-toutiao.com` | 4 | 穿山甲 | 素材包签名 |
| `sf6-fe-tos.pglstatp-toutiao.com` | 3 | 穿山甲 | 素材包 CDN |
| `v26-be-pack.pglstatp-toutiao.com` | 1 | 穿山甲 | 素材包 |
| `huichuan-mc.sm.cn` | 1 | 神马 | 「汇川」广告 SDK |
| `image.uczzd.cn` | 1 | UC / 神马 | 广告素材图床 |

加上实际发起请求的 `sdk.1rtb.net`，**广告域名共 14 个，分属 4 个广告生态**：

1. **1RTB** —— 独立广告 SDK
2. **穿山甲 / 巨量引擎** —— 字节跳动广告联盟
3. **阿里妈妈 / TanX** —— 阿里自家广告体系
4. **神马 / UC 汇川** —— 阿里系搜索广告

穿山甲那 5 个子域全部落在 `pglstatp-toutiao.com` 之下，一条 `DOMAIN-SUFFIX` 就能收掉。

### 3.2 统计与埋点（8 个，默认不拦）

| 域名 | 次数 |
|---|---:|
| `cainiao-app-logs.cn-zhangjiakou.log.aliyuncs.com` | 46 |
| `gm.mmstat.com` | 37 |
| `nbnetflow-reply-log.cn-wulanchabu.log.aliyuncs.com` | 17 |
| `s-gm.mmstat.com` | 6 |
| `report-user-online-event.cn-wulanchabu.log.aliyuncs.com` | 4 |
| `mazu.m.qq.com` | 3 |
| `log.mmstat.com` | 1 |
| `acjs.aliyun.com` | 1 |

这些是统计/日志，不是广告。插件里以注释形式提供，需要时自行打开。

### 3.3 设备指纹 / 风控（3 个，**绝对不拦**）

| 域名 | 次数 |
|---|---:|
| `ynuf.aliapp.org` | 9 |
| `fourier.taobao.com` | 7 |
| `fourier.alibaba.com` | 5 |

`fourier` / `ynuf` 是阿里的设备指纹体系。拦掉等于告诉风控「这台设备行为异常」，
有可能触发验证码、限流甚至降权。**收益极低，风险很高，不碰。**

### 3.4 业务必需（44 个）

`*.cainiao.com` 各 mtop 网关、`*.alicdn.com`、`*.m.taobao.com`、`amap`、`alipayobjects`
等，全部保留。

---

## 四、那条真实的广告请求

```
POST http://sdk.1rtb.net/sdk/req_ad
     ?sdk_version=2.7.18.1&device_os=iOS&accept_ad_type=4
     &app_id=116352&pid=1089329&sdk_version_code=2071801
Content-Type: application/x-www-form-urlencoded
MS-SDK-Version: iOS-2.7.18.1
User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) ...

body: base64(enc=3&nonce=...&signature=...&message=...)
```

关键参数：

- `app_id=116352` —— 菜鸟在 1RTB 平台的媒体 ID
- `pid=1089329` —— 广告位 ID
- `accept_ad_type=4` —— 接受的广告类型

响应：`status 0`、`size 0`，**空返回**。该广告位当时没有填充。

插件里拦 `1rtb.net`，效果是让 SDK 连不上、直接走失败分支，广告容器不会被拉起。

---

## 五、插件的设计取舍

1. **纯 `[Rule]` 域名级拦截，不用 MITM。**
   本次所有广告流量都是独立域名，没有任何一条走业务域的 URL 路径。
   既然域名级就够，就没必要引入 MITM —— 省掉装证书这一步，也省掉证书过期、
   SSL Pinning 冲突这类问题。

2. **不用脚本改响应。**
   改 MTop 返回的广告位 JSON 需要 MITM + 逐个接口适配，而广告位接口在本次抓包里
   一条都没出现（全被 amdc 噪音盖住了）。没有证据支撑的改写是猜测，不做。

3. **`REJECT` 而不是 `REJECT-DROP`。**
   `REJECT` 立刻回 RST，广告 SDK 快速走失败分支；`REJECT-DROP` 静默丢包，
   SDK 会卡在超时重试上，反而拖慢界面。

4. **阿里云日志域名用 exact host，不用后缀。**
   `admonitor-feedback.cn-hangzhou.log.aliyuncs.com` 只能精确匹配。
   写成 `log.aliyuncs.com` 会连带干掉阿里云上所有业务日志。

---

## 六、这份分析的局限

- 只覆盖了**一次**抓包、**一个**页面路径。菜鸟不同页面（首页、我的、活动页）
  可能拉不同的广告位，域名集合会更大。
- 广告域名全部来自 **dispatch 列表**而非实际请求。它证明了「App 里有这些 SDK 且在
  预热」，但不能证明「每个域名都真的加载了广告」。
- 抓包时长未知，1RTB 那条返回空也说明广告位可能没填充，样本偏薄。
- 建议：多抓几个页面（首页下滑、领券中心、签到页）再跑一遍 `tools/analyze_har.py`，
  把新出现的广告域名补进规则。
