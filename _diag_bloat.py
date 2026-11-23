# -*- coding: utf-8 -*-
"""诊断输出 token 膨胀：看产物里各字段的实际长度。"""
import json, glob, os

for fp in ["G:/_setup/_ann/out_v3t/hy3/batch_0007.json",
           "G:/_setup/_ann/out_v3t/ds/batch_0002.json"]:
    if not os.path.exists(fp):
        print("缺:", fp); continue
    raw = open(fp, encoding="utf-8").read()
    o = json.loads(raw)
    items = o.get("items") if isinstance(o, dict) else o
    print("\n### %s  文件 %d B  条目 %d" % (os.path.basename(fp), len(raw), len(items)))
    longest = []
    for it in items:
        for k in ("pause", "stress", "rate"):
            v = it.get(k)
            if v is None:
                continue
            for rec in (v if isinstance(v, list) else [v]):
                if isinstance(rec, dict):
                    for kk, vv in rec.items():
                        if isinstance(vv, str) and len(vv) > 40:
                            longest.append((len(vv), k + "." + kk, vv[:160]))
    longest.sort(reverse=True)
    print("  超 40 字符的文本字段 %d 个，最长 5 个：" % len(longest))
    for ln, path, s in longest[:5]:
        print("    %5d  %-14s %s" % (ln, path, s.replace("\n", " ")))
    # 键统计
    keys = set()
    for it in items:
        keys |= set(it.keys())
    print("  条目的键:", sorted(keys))
    print("  首条样例:", json.dumps(items[0], ensure_ascii=False)[:400])
