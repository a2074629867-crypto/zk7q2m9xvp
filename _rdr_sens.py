# -*- coding: utf-8 -*-
"""RDR 对最小词数的敏感性：短单元语速估计噪声大，看结论是否被它们撑起来。"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np

d = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
rows = {r["uid"]: r for r in d["rows"]}
seams = d["seams"]

print("%-10s %6s %6s %7s %8s %10s" % ("最小词数", "接缝", "超标", "超标%", "涉及组", "RDR"))
for mw in (3, 4, 5, 6, 8, 10):
    sel = [s for s in seams if rows[s["a"]]["w"] >= mw and rows[s["b"]]["w"] >= mw]
    bad = [s for s in sel if s["ratio"] > 1.5]
    gp = {s["pid"] for s in sel}
    print("%-10d %6d %6d %6.0f%% %8d %10.3f"
          % (mw, len(sel), len(bad), 100*len(bad)/max(1,len(sel)),
             len({s["pid"] for s in bad}), len({s["pid"] for s in bad})/max(1,len(gp))))

# 单元词数分布 & 超标接缝的词数分布
ws = [r["w"] for r in d["rows"]]
print("\n单元词数 p10/p50/p90 = %d / %d / %d" % tuple(int(np.percentile(ws, p)) for p in (10,50,90)))
bad = [s for s in seams if s["ratio"] > 1.5]
print("超标接缝两端词数 p10/p50/p90 = %d / %d / %d"
      % tuple(int(np.percentile([rows[s["a"]]["w"] for s in bad] + [rows[s["b"]]["w"] for s in bad], p))
              for p in (10,50,90)))

# 词数>=8 的硬骨头
sel = [s for s in seams if rows[s["a"]]["w"] >= 8 and rows[s["b"]]["w"] >= 8]
bad8 = [s for s in sel if s["ratio"] > 1.5]
print("\n两端都>=8 词且超标 %d 条：" % len(bad8))
for s in sorted(bad8, key=lambda s: -s["ratio"]):
    print("  段%-3d %s(%dw)→%s(%dw)  %.2f×  %s"
          % (s["pid"], s["a"], rows[s["a"]]["w"], s["b"], rows[s["b"]]["w"],
             s["ratio"], "重生成 " + s["culprit"]))
