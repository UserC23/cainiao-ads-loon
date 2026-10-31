#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菜鸟 App HAR 抓包分析工具

用途：从 Loon / Stream / Charles 导出的 HAR 里定位广告，辅助维护 Loon 插件规则。

用法：
    python analyze_har.py <file.har>              # 总览
    python analyze_har.py <file.har> --check      # 先看 MITM 到底有没有生效
    python analyze_har.py <file.har> --hosts      # 实际请求域名排行
    python analyze_har.py <file.har> --dispatch   # 解码 AMDC 调度，列出调度域名
    python analyze_har.py <file.har> --scan-ads   # 遍历 JSON 响应，定位广告字段路径
    python analyze_har.py <file.har> --ads        # 只看广告域名（域名层）
    python analyze_har.py <file.har> --all        # 全部

核心知识点：
    1. amdc.m.taobao.com/amdc/mobileDispatch 是阿里 MTop 的「域名调度中心」，
       不是广告接口。拦掉会让 App 大面积解析失败。
    2. 它的请求体是两层编码：base64( urlencode表单 )，表单里 domain 字段可能是
       多个域名用空格分隔。
    3. 响应也是 base64(JSON)，dns[].um == 1 表示有真实解析，um == 3 表示
       servers 为空（走本地 DNS）。
    4. Loon 导出的 HAR 只包含「看得到完整内容」的请求。如果整份 HAR 里
       一条 https 都没有，说明 MITM 没解密 —— 插件里的 [Rewrite] 全部不会执行，
       这时候分析广告字段是没有意义的。
"""

import argparse
import base64
import collections
import json
import re
import sys
import urllib.parse

AMDC_PATH = "/amdc/mobileDispatch"

# 广告域名特征。命中即视为广告链路，命中后仍需人工确认归属。
AD_PATTERN = re.compile(
    r"(1rtb"
    r"|tanx\.com"
    r"|adashx"
    r"|admonitor"
    r"|adservice"
    r"|pglstatp|pangolin|pgdt|ugdtimg"
    r"|ctobsnssdk|douyinpic"
    r"|huichuan|uczzd|sm\.cn"
    r"|alimama|mmstat.*ad"
    r"|ad\.|ads\.|/ad/|/ads/)",
    re.I,
)

# 绝不该拦的域名：设备指纹 / 风控 / 调度。命中时给出警告。
PROTECTED_PATTERN = re.compile(
    r"(^amdc\.|ynuf\.|fourier\.|umid\.|sec\.taobao)", re.I
)

# 统计埋点，可拦但非广告
STATS_PATTERN = re.compile(
    r"(mmstat\.com|mazu\.|acjs\.|log\.aliyuncs\.com|\.log\.)", re.I
)

# 业务主域：出现这些才说明抓到了真正的业务流量
BIZ_HOST_PATTERN = re.compile(
    r"(cainiao\.com|guide-acs\.m\.taobao\.com|acs\.m\.taobao\.com|h5api\.m\.taobao\.com)",
    re.I,
)

# JSON 里「像广告」的键名
AD_KEY_PATTERN = re.compile(
    r"^(ads?|adInfo|adData|adJson|adList|adItems|adMaterial|adMaterialId"
    r"|adZoneId|adExpInfo|adBanner|adCard|adTrack|cpcInfo|cpcinfo)$",
    re.I,
)

# JSON 里「像广告」的取值（卡片类型标记）
AD_VALUE_PATTERN = re.compile(
    r"^(ad|ads|advert|advertise|advertisement|cpc|spm_ad)$", re.I
)

# JSON 里「像广告位」的标题
AD_TITLE_PATTERN = re.compile(
    r"热门活动|活动中心|活动专区|领券中心|福利中心|签到有礼|为你推荐|猜你喜欢|广告"
)

TITLE_KEYS = ("title", "name", "moduleName", "headerTitle", "text", "desc")
TYPE_KEYS = ("cardType", "bizType", "itemType", "templateType", "recommendType", "type")


def b64_decode(text):
    """宽松 base64 解码，失败返回 None。"""
    if not text:
        return None
    s = text.strip()
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s).decode("utf-8", "replace")
    except Exception:
        return None


def host_of(url):
    if "://" in url:
        try:
            return urllib.parse.urlsplit(url).netloc
        except Exception:
            return "?"
    return "?"


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["log"]["entries"]


def resp_text(entry):
    """取出响应体文本，兼容 base64 编码的 content。"""
    content = entry.get("response", {}).get("content") or {}
    text = content.get("text")
    if not text:
        return None
    if content.get("encoding") == "base64":
        decoded = b64_decode(text)
        return decoded
    return text


def try_json(entry):
    text = resp_text(entry)
    if not text:
        return None
    head = text.lstrip()[:1]
    if head not in "{[":
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


# ── 子命令 ───────────────────────────────────────────────────


def cmd_check(entries):
    """判断这份抓包里 MITM 有没有真的解密。"""
    schemes = collections.Counter(
        e["request"]["url"].split(":", 1)[0] for e in entries
    )
    https_entries = [e for e in entries if e["request"]["url"].startswith("https://")]
    biz = [e for e in https_entries if BIZ_HOST_PATTERN.search(host_of(e["request"]["url"]))]

    print("\n=== MITM 自检 ===")
    for s, c in schemes.most_common():
        print(f"  {s:6s}  {c}")

    if not https_entries:
        print("\n❌ 没有任何 HTTPS 请求 —— MITM 完全没有解密。")
        print("   这意味着插件里的 [Rewrite] 一条都不会执行，此时分析广告字段没有意义。")
        print("   先按 docs/mitm-guide.md 第三节把 MITM 修好，再重新抓包。")
        return False

    if not biz:
        print(f"\n⚠️  有 {len(https_entries)} 条 HTTPS，但没有一条是菜鸟/淘宝业务域。")
        print("   常见原因：[MITM] hostname 没覆盖到业务网关。")
        return False

    print(f"\n✅ 解密正常：{len(https_entries)} 条 HTTPS，其中 {len(biz)} 条命中业务域。")
    hosts = collections.Counter(host_of(e["request"]["url"]) for e in biz)
    for h, c in hosts.most_common(10):
        print(f"  {c:5d}  {h}")
    return True


def cmd_hosts(entries):
    hosts = collections.Counter(host_of(e["request"]["url"]) for e in entries)
    print(f"\n=== 实际请求域名 {len(hosts)} 个 ===")
    for h, c in hosts.most_common():
        print(f"{c:6d}  {h}")
    return hosts


def cmd_dispatch(entries):
    """解码 AMDC 调度请求，返回 {域名: 次数}。"""
    counter = collections.Counter()
    hits = 0
    for e in entries:
        req = e["request"]
        if AMDC_PATH not in req["url"]:
            continue
        hits += 1
        decoded = b64_decode((req.get("postData") or {}).get("text"))
        if not decoded:
            continue
        qs = urllib.parse.parse_qs(decoded, keep_blank_values=True)
        for raw in qs.get("domain", []):
            for one in raw.split():
                one = one.strip()
                if one:
                    counter[one] += 1
    print(f"\n=== AMDC 调度请求 {hits} 条，涉及域名 {len(counter)} 个 ===")
    for d, c in counter.most_common():
        tag = ""
        if PROTECTED_PATTERN.search(d):
            tag = "  [风控/调度·勿拦]"
        elif AD_PATTERN.search(d):
            tag = "  [广告]"
        elif STATS_PATTERN.search(d):
            tag = "  [统计]"
        print(f"{c:6d}  {d}{tag}")
    return counter


def _walk(node, path="$"):
    """递归产出 (路径, 值)。"""
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def cmd_scan_ads(entries):
    """遍历 JSON 响应，定位广告字段路径，直接给出 jq 建议。"""
    json_entries = []
    for e in entries:
        obj = try_json(e)
        if obj is not None:
            json_entries.append((e, obj))

    print(f"\n=== 可解析的 JSON 响应 {len(json_entries)} 条 ===")
    if not json_entries:
        print("（无）—— 如果 --check 也显示没有 HTTPS，那就是 MITM 没生效，先修 MITM。")
        return

    hits = 0
    for e, obj in json_entries:
        url = e["request"]["url"]
        found = []

        for path, val in _walk(obj):
            # 1) 键名像广告
            key = path.rsplit(".", 1)[-1]
            if AD_KEY_PATTERN.search(key):
                found.append((path, f"广告字段名 {key}"))
                continue
            if not isinstance(val, dict):
                continue
            # 2) 卡片类型标记为 ad
            for tk in TYPE_KEYS:
                tv = val.get(tk)
                if isinstance(tv, str) and AD_VALUE_PATTERN.search(tv):
                    found.append((f"{path}.{tk}", f"卡片类型 = {tv}"))
                    break
            # 3) 标题像广告位
            for tk in TITLE_KEYS:
                tv = val.get(tk)
                if isinstance(tv, str) and AD_TITLE_PATTERN.search(tv):
                    found.append((f"{path}.{tk}", f"标题 = {tv}"))
                    break

        if not found:
            continue
        hits += 1
        print(f"\n--- {host_of(url)}{urllib.parse.urlsplit(url).path[:90]}")
        print(f"    size={len(resp_text(e) or '')}B")
        seen = set()
        for path, why in found[:25]:
            if path in seen:
                continue
            seen.add(path)
            print(f"    {path}")
            print(f"        ← {why}")

    if not hits:
        print("\n没有命中明显的广告字段。可能接口改了命名，用 --all 先看域名全貌人工翻。")
    else:
        print(f"\n命中 {hits} 条响应。把上面的路径填进插件：")
        print("  ^https?://[^/]+/gw/mtop\\.  response-body-json-jq 'del(路径)'")
        print("  路径写法：$.data.data.modules[3] → .data.data.modules[3]")


def cmd_ads(entries):
    counter = collections.Counter()
    for e in entries:
        req = e["request"]
        if AMDC_PATH in req["url"]:
            decoded = b64_decode((req.get("postData") or {}).get("text"))
            if decoded:
                qs = urllib.parse.parse_qs(decoded, keep_blank_values=True)
                for raw in qs.get("domain", []):
                    for one in raw.split():
                        if one and AD_PATTERN.search(one):
                            counter[one] += 1
            continue
        h = host_of(req["url"])
        if AD_PATTERN.search(req["url"]):
            counter[h] += 1

    print(f"\n=== 广告相关域名 {len(counter)} 个 ===")
    if not counter:
        print("（无）")
        return counter
    for d, c in counter.most_common():
        if PROTECTED_PATTERN.search(d):
            continue
        print(f"{c:6d}  {d}")

    print("\n--- 候选规则（需人工收窄，勿直接全量粘贴）---")
    print("# 提示：共享域/CDN 域名（如 *.log.aliyuncs.com、*.douyinpic.com）")
    print("#       应改为精确 DOMAIN，否则会连带干掉同域下的正常业务。")
    for d, _ in counter.most_common():
        if PROTECTED_PATTERN.search(d):
            print(f"# 跳过（风控）：{d}")
            continue
        print(f"DOMAIN-SUFFIX,{d},REJECT")
    return counter


def cmd_summary(entries):
    print(f"请求总数: {len(entries)}")
    print("协议:", dict(collections.Counter(
        e["request"]["url"].split(":", 1)[0] for e in entries)))
    print("响应状态:", dict(collections.Counter(e["response"]["status"] for e in entries)))
    print("MIME:", dict(collections.Counter(
        e["response"]["content"].get("mimeType") for e in entries)))

    bad = [e for e in entries if e["response"]["status"] == 0]
    if bad:
        print(f"\n未完成请求 {len(bad)} 条:")
        for e in bad[:5]:
            print("  ", e["request"]["method"], e["request"]["url"][:120])


def main():
    ap = argparse.ArgumentParser(
        description="菜鸟 App HAR 抓包分析，辅助维护 Loon 去广告插件")
    ap.add_argument("har", help="HAR 文件路径")
    ap.add_argument("--check", action="store_true", help="检查 MITM 是否真的解密（先跑这个）")
    ap.add_argument("--hosts", action="store_true", help="实际请求域名排行")
    ap.add_argument("--dispatch", action="store_true", help="解码 AMDC 调度域名")
    ap.add_argument("--scan-ads", action="store_true", help="遍历 JSON 响应定位广告字段")
    ap.add_argument("--ads", action="store_true", help="只看广告域名并生成规则候选")
    ap.add_argument("--all", action="store_true", help="执行全部")
    args = ap.parse_args()

    try:
        entries = load(args.har)
    except FileNotFoundError:
        print(f"文件不存在: {args.har}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"HAR 解析失败: {exc}", file=sys.stderr)
        return 2

    if not any([args.check, args.hosts, args.dispatch, args.scan_ads, args.ads, args.all]):
        cmd_summary(entries)
        print("\n建议下一步：--check 确认 MITM 生效，再 --scan-ads 定位广告字段")
        return 0

    if args.all or args.check:
        cmd_check(entries)
    if args.all or args.hosts:
        cmd_hosts(entries)
    if args.all or args.dispatch:
        cmd_dispatch(entries)
    if args.all or args.scan_ads:
        cmd_scan_ads(entries)
    if args.all or args.ads:
        cmd_ads(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
