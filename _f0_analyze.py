# -*- coding: utf-8 -*-
"""对 f0_crosscheck 全量结果做四象限归因：
   A 双估计器都≥2突跳   → 真缺陷（值得重生成）
   B 只有 praat ≥2      → praat 跟踪噪声
   C 只有 pyin ≥2       → pyin 噪声
   D 两者都<2           → 账本判据误报（WATCH/FIX 该撤）
另外按 verdict 分 WATCH / FIX 两档分别统计。
"""
import json
from collections import Counter

P = "G:/_setup/_f0_crosscheck.json"
rows = json.load(open(P, encoding="utf-8"))
print("读入 %d 条\n" % len(rows))

def cls(r):
    a, b = r["praat_n"] >= 2, r["pyin_n"] >= 2
    if a and b:
        return "A_双估计器"
    if a:
        return "B_仅praat"
    if b:
        return "C_仅pyin"
    return "D_都无突跳"

print("%-14s %6s %6s %6s %6s %6s" % ("类别", "总数", "WATCH", "FIX", "PASS", "占比"))
tot = Counter()
for r in rows:
    tot[cls(r)] += 1
for k in sorted(tot):
    sub = [r for r in rows if cls(r) == k]
    v = Counter(x["verdict"] for x in sub)
    print("%-14s %6d %6d %6d %6d %5.1f%%"
          % (k, len(sub), v["WATCH"], v["FIX"], v["PASS"], 100.0 * len(sub) / len(rows)))

print("\n--- 真缺陷候选（A 类，med F0 与突跳幅度）---")
a = sorted([r for r in rows if cls(r) == "A_双估计器"],
           key=lambda r: -max(r["praat_max"], r["pyin_max"]))
for r in a[:15]:
    print("  %-9s %-6s praat %d次/%.1f  pyin %d次/%.1f  med %.0f/%.0f"
          % (r["unit"], r["verdict"], r["praat_n"], r["praat_max"],
             r["pyin_n"], r["pyin_max"], r["praat_med"], r["pyin_med"]))
print("  ... 合计 %d 条" % len(a))

print("\n--- 中位 F0 对照（判「高音帧」是否成立）---")
hi = [r for r in rows if r["praat_med"] > 305 or r["pyin_med"] > 305]
print("  中位 F0 > 305Hz 的条数: %d（红线：F0>305 就是喊）" % len(hi))
for r in hi[:10]:
    print("    %-9s praat_med=%.0f pyin_med=%.0f %s"
          % (r["unit"], r["praat_med"], r["pyin_med"], r["verdict"]))
