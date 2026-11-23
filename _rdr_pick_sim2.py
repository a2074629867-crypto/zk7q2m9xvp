# -*- coding: utf-8 -*-
"""分档：只用无标签 take（1234/42）vs 含 rate 标签版，分别能降到多少。"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np

g = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
T = {o["uid"]: o for o in json.load(open("_rdr_takes.json", encoding="utf-8"))}
S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]
by = {}
for r in g["rows"]:
    if r["pid"] is not None:
        by.setdefault(r["pid"], []).append(dict(r))
for k in by:
    by[k].sort(key=lambda r: r["uid"])

def seams_of(m):
    out = []
    for pid, grp in by.items():
        for i in range(len(grp) - 1):
            a, b = grp[i]["uid"], grp[i + 1]["uid"]
            ra, rb = m.get(a), m.get(b)
            if ra and rb:
                out.append((pid, a, b, max(ra, rb) / min(ra, rb)))
    return out

def stat(tag, m):
    s = seams_of(m); r = np.array([x[3] for x in s])
    bad = {x[0] for x in s if x[3] > 1.5}
    print("%-28s 超1.5 %3d (%3.0f%%)  p50 %.2f  p75 %.2f  p90 %.2f  max %.2f  RDR %.3f"
          % (tag, int((r > 1.5).sum()), 100*(r > 1.5).mean(),
             np.median(r), np.percentile(r,75), np.percentile(r,90), r.max(),
             len(bad)/len({x[0] for x in s})))

base = {u: r["rate_B"] for u, r in ((x["uid"], x) for x in g["rows"])}

# 目标 = 相邻单元（原状）语速中位
def target_of(uid):
    for pid, grp in by.items():
        ids = [x["uid"] for x in grp]
        if uid not in ids: continue
        i = ids.index(uid)
        nb = []
        if i > 0: nb.append(grp[i-1]["rate_B"])
        if i+1 < len(grp): nb.append(grp[i+1]["rate_B"])
        return float(np.median(nb)) if nb else None
    return None

m_clean = dict(base)   # 只在 1234/42 里选
m_all = dict(base)     # 含 rate
picks = []
for u, o in T.items():
    t = target_of(u)
    if not t: continue
    clean = {k: v for k, v in o["cand"].items() if k in ("1234", "42")}
    b_clean = min(clean.items(), key=lambda kv: abs(np.log(kv[1]/t))) if clean else (None, None)
    b_all = min(o["cand"].items(), key=lambda kv: abs(np.log(kv[1]/t))) if o["cand"] else (None, None)
    if b_clean[1]: m_clean[u] = b_clean[1]
    if b_all[1]:  m_all[u] = b_all[1]
    picks.append(dict(uid=u, pid=o["pid"], w=o["w"], target=round(t,1), cur=o["cur"],
                      clean_seed=b_clean[0], clean_rate=b_clean[1],
                      all_seed=b_all[0], all_rate=b_all[1],
                      rate_only=(b_all[0] == "rate" and b_clean[0] != "rate")))

print("阈值 1.5×（马修同口径：超 13%，p90 1.55）\n")
stat("原状", base)
stat("只在 1234/42 里选", m_clean)
stat("含 rate 标签版", m_all)
n_rate = sum(1 for p in picks if p["rate_only"])
print("\n最佳解落在 rate take 上的：%d 条 → %s"
      % (n_rate, [p["uid"] for p in picks if p["rate_only"]]))
print("换 take 后仍超标（无标签口径）：")
sc = seams_of(m_clean); sb = seams_of(base)
for pid, a, b, r in sorted(sc, key=lambda x: -x[3]):
    if r > 1.5:
        old = next(x[3] for x in sb if x[0] == pid and x[1] == a)
        print("  段%-3d %s→%s  %.2f → %.2f" % (pid, a, b, old, r))
json.dump(picks, open("_rdr_picks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
