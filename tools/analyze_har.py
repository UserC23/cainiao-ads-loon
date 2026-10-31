#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菜鸟 App HAR 抓包分析工具

用途：从 Loon / Stream / Charles 导出的 HAR 里，找出广告相关域名，辅助维护 Loon 插件规则。

用法：
    python analyze_har.py <file.har>              # 总览
    python analyze_har.py <file.har> --hosts      # 实际请求域名排行
    python analyze_har.py <file.har> --dispatch   # 解码 AMDC 调度，列出全部调度域名
    python analyze_har.py <file.har> --ads        # 只看广告相关域名
    python analyze_har.py <file.har> --all        # 以上全部

核心知识点：
    1. amdc.m.taobao.com/amdc/mobileDispatch 是阿里 MTop 的「域名调度中心」，
       不是广告接口。拦掉会让 App 大面积解析失败。
    2. 它的请求体是两层编码：base64( urlencode表单 )，表单里 domain 字段可能是
       多个域名用空格分隔。
    3. 响应也是 base64(JSON)，dns[].um == 1 表示有真实解析，um == 3 表示
       servers 为空（走本地 DNS）。本次抓包绝大多数是 um 3。
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
        # 第一层解出来还是 urlencode 表单
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
    creators = {}
    for e in entries[:1]:
        pass
    print("响应状态:", dict(collections.Counter(e["response"]["status"] for e in entries)))
    print("MIME:", dict(collections.Counter(
        e["response"]["content"].get("mimeType") for e in entries)))

    # 未完成的请求
    bad = [e for e in entries if e["response"]["status"] == 0]
    if bad:
        print(f"\n未完成请求 {len(bad)} 条:")
        for e in bad[:5]:
            print("  ", e["request"]["method"], e["request"]["url"][:120])


def main():
    ap = argparse.ArgumentParser(
        description="菜鸟 App HAR 抓包分析，辅助维护 Loon 去广告插件")
    ap.add_argument("har", help="HAR 文件路径")
    ap.add_argument("--hosts", action="store_true", help="实际请求域名排行")
    ap.add_argument("--dispatch", action="store_true", help="解码 AMDC 调度域名")
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

    if not any([args.hosts, args.dispatch, args.ads, args.all]):
        cmd_summary(entries)
        print("\n提示：加 --all 查看域名全貌")
        return 0

    if args.all or args.hosts:
        cmd_hosts(entries)
    if args.all or args.dispatch:
        cmd_dispatch(entries)
    if args.all or args.ads:
        cmd_ads(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
