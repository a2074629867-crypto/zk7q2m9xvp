# -*- coding: utf-8 -*-
"""比较剪辑前后 w2v 覆盖率，确认「剪停顿 + 填底噪」没有切到字。"""
import io
import json
import statistics

pre = json.load(io.open("_final9_summary.json", encoding="utf-8"))
post = {r["id"]: (r.get("w2v_cov") or 0.0)
        for r in json.load(io.open("_align_final9.json", encoding="utf-8"))}

pairs = [(k, pre[k]["cov"], post[k]) for k in post if k in pre]
worse = [p for p in pairs if p[2] < p[1] - 0.08]
d = [p[2] - p[1] for p in pairs]

print("可比 %d 条；覆盖率下降 >0.08 的 %d 条" % (len(pairs), len(worse)))
for k, x, y in sorted(worse, key=lambda t: t[2] - t[1])[:12]:
    print("   %-9s %.2f -> %.2f" % (k, x, y))
print("变化 中位 %+.3f 均值 %+.3f" % (statistics.median(d), sum(d) / len(d)))
print("剪后 cov>=0.85: %d / 239" % sum(1 for k in post if post[k] >= 0.85))
