# -*- coding: utf-8 -*-
"""生成换 take 计划 + 声纹 manifest。

规则：只在无标签 take（1234 / 42）里选，且必须真的换（seed 不同）。
"""
import sys, json, os
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

def target_of(uid):
    for pid, grp in by.items():
        ids = [x["uid"] for x in grp]
        if uid not in ids: continue
        i = ids.index(uid); nb = []
        if i > 0: nb.append(grp[i-1]["rate_B"])
        if i+1 < len(grp): nb.append(grp[i+1]["rate_B"])
        return float(np.median(nb)) if nb else None
    return None

plan, man = [], []
for u, o in T.items():
    t = target_of(u)
    if not t: continue
    clean = {k: v for k, v in o["cand"].items() if k in ("1234", "42")}
    if not clean: continue
    seed, rate = min(clean.items(), key=lambda kv: abs(np.log(kv[1]/t)))
    cur_seed = str((S[u].get("pick") or {}).get("seed"))
    if seed == cur_seed:
        continue
    a = os.path.join("_mt_raw_s" + cur_seed, u + ".wav")
    b = os.path.join("_mt_raw_s" + seed, u + ".wav")
    if not (os.path.exists(a) and os.path.exists(b)):
        print("缺文件", u, a, b); continue
    plan.append(dict(uid=u, pid=o["pid"], w=o["w"], target=round(t,1),
                     old_seed=cur_seed, old_rate=o["cur"],
                     new_seed=seed, new_rate=rate,
                     old_dev=round(float(abs(np.log(o["cur"]/t))),3),
                     new_dev=round(float(abs(np.log(rate/t))),3),
                     a=a, b=b))
    man.append(dict(uid=u, a=a, b=b))

print("要换 %d 条（无标签 take 之间）\n" % len(plan))
print("%-7s %4s %6s %6s %-6s %6s %-6s %6s %s"
      % ("uid","词","目标","旧","seed","旧偏","新","新偏","新seed"))
for p in sorted(plan, key=lambda p: -(p["old_dev"]-p["new_dev"])):
    print("%-7s %4d %6.0f %6.0f %-6s %6.2f %6.0f %6.2f %s"
          % (p["uid"], p["w"], p["target"], p["old_rate"], p["old_seed"],
             p["old_dev"], p["new_rate"], p["new_dev"], p["new_seed"]))
json.dump(plan, open("_rdr_swap_plan.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(man, open("_rdr_swap_manifest.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n写 _rdr_swap_plan.json / _rdr_swap_manifest.json")
