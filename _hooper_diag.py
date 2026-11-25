# -*- coding: utf-8 -*-
"""看 Thomas 低覆盖率条目的 miss 具体是什么，区分「真吞字」和「ASR 听错/文本口径」。"""
import json
import re

d = json.load(open("G:/_setup/_hooper_cov.json", encoding="utf-8"))
rows = json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))
txt = {r["id"]: r["text"] for r in rows}

items = sorted(d["Thomas"]["items"], key=lambda x: x["cov"])
print("%-9s %5s %6s %-5s %s" % ("id", "cov", "wpm", "nword", "缺的词"))
for x in items[:26]:
    print("%-9s %5.2f %6s %5d  %s" % (x["id"], x["cov"],
                                      ("%.0f" % x["wpm"]) if x["wpm"] else "-",
                                      x["words"], x["miss"]))
print()
print("=== 抽查 5 条原文 vs ASR ===")
for x in items[:5]:
    print("\n[%s] cov=%.2f" % (x["id"], x["cov"]))
    print("  ref: %s" % txt[x["id"]][:150])
    print("  hyp: %s" % x["hyp"][:150])

# 统计 miss 的词频：如果集中在 the/a/of/and 这类，更像真吞；如果是专名/人名，像 ASR 错
import collections
c = collections.Counter()
for x in d["Thomas"]["items"]:
    for w in x["miss"]:
        c[w] += 1
print("\n=== Thomas 全部 miss 词频 top25 ===")
for w, n in c.most_common(25):
    print("  %-14s %d" % (w, n))
