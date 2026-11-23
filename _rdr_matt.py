# -*- coding: utf-8 -*-
"""马修母带的相邻句语速比，作为 RDR 的人工朗读基线。"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np

S = json.load(open("_matt_sents.json", encoding="utf-8"))
rows = []
for i, s in enumerate(S):
    if len(s) < 3:
        continue
    t0 = s[0][0]; t1 = s[-1][1]
    eff = t1 - t0
    if eff < 0.4:
        continue
    rows.append(dict(i=i, w=len(s), eff=round(eff, 3), rate=len(s) / eff * 60))

r = np.array([x["rate"] for x in rows])
print("马修句级语速  n=%d  p10/p50/p90 = %.0f / %.0f / %.0f wpm" %
      (len(r), np.percentile(r, 10), np.median(r), np.percentile(r, 90)))

# 相邻句比（只算时长可比的中长句）
for minw in (3, 5, 8):
    sel = [x for x in rows if x["w"] >= minw]
    ratios = [max(sel[i]["rate"], sel[i+1]["rate"]) / min(sel[i]["rate"], sel[i+1]["rate"])
              for i in range(len(sel) - 1)]
    ratios = np.array(ratios)
    print("  相邻句 w>=%d : n=%d  p50 %.2f  p90 %.2f  max %.2f   超1.5 的 %.1f%%" %
          (minw, len(ratios), np.median(ratios), np.percentile(ratios, 90),
           ratios.max(), 100 * (ratios > 1.5).mean()))
