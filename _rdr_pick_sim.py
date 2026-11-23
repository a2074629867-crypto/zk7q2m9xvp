# -*- coding: utf-8 -*-
"""模拟：全部 culprit 换成「离邻居最近」的 take 后，接缝比与 RDR 会变成什么样。

只换已有 take，不生成任何东西。用于判断 RDR 当"选 take 判据"值不值。
"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np

g = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
T = {o["uid"]: o for o in json.load(open("_rdr_takes.json", encoding="utf-8"))}
rows = {r["uid"]: dict(r) for r in g["rows"]}
by = {}
for r in g["rows"]:
    if r["pid"] is not None:
        by.setdefault(r["pid"], []).append(dict(r))
for k in by:
    by[k].sort(key=lambda r: r["uid"])

def seams_of(rate_map):
    """rate_map: uid->rate。返回接缝列表（pid, a, b, ratio）。"""
    out = []
    for pid, grp in by.items():
        for i in range(len(grp) - 1):
            a, b = grp[i]["uid"], grp[i + 1]["uid"]
            ra, rb = rate_map.get(a), rate_map.get(b)
            if not ra or not rb:
                continue
            out.append((pid, a, b, max(ra, rb) / min(ra, rb)))
    return out

def rdr(seams, thr=1.5):
    bad = {p for p, a, b, r in seams if r > thr}
    return len(bad) / max(1, len({p for p, a, b, r in seams}))

base = {u: r["rate_B"] for u, r in rows.items()}

# 方案1：只换 culprit 里的 best take
m1 = dict(base)
for u, o in T.items():
    if o["best_rate"]:
        m1[u] = o["best_rate"]

# 方案2：全局每单元都选 best（含非 culprit，用已有的 1234/42 两 take）
m2 = dict(base)

def stat(tag, seams):
    r = np.array([s[3] for s in seams])
    over = (r > 1.5).mean()
    print("%-26s 接缝 %3d  超1.5 %3d (%4.0f%%)  p50 %.2f  p90 %.2f  max %.2f  RDR %.3f"
          % (tag, len(r), int((r > 1.5).sum()), 100 * over,
             np.median(r), np.percentile(r, 90), r.max(), rdr(seams)))

print("阈值 1.5×\n")
stat("原状（当前 pick）", seams_of(base))
stat("换 culprit 的 best take", seams_of(m1))

# 逐条看改善
print("\n换 take 后仍超标的接缝：")
for pid, a, b, r in sorted(seams_of(m1), key=lambda s: -s[3]):
    if r > 1.5:
        old = next(x[3] for x in seams_of(base) if x[0] == pid and x[1] == a)
        print("  段%-3d %s→%s  %.2f × → %.2f ×   %s"
              % (pid, a, b, old, r, "改善" if r < old else "无改善"))

fixed = [(p, a, b, o, n) for (p, a, b, n) in seams_of(m1)
         for (p2, a2, b2, o) in seams_of(base) if p2 == p and a2 == a and o > 1.5 >= n]
print("\n由超标变达标 %d 条：%s" % (len(fixed), [(p, a, b, round(o,2), round(n,2)) for p,a,b,o,n in fixed]))
json.dump(dict(base_rdr=rdr(seams_of(base)), pick_rdr=rdr(seams_of(m1)),
               rate_map=m1), open("_rdr_pick_sim.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
