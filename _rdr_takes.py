# -*- coding: utf-8 -*-
"""在已有 take 池里找语速更接近邻居的版本（零成本，不用重新生成）。

对每个 culprit：
  目标语速 target = 同段相邻单元语速的中位（排除自己）
  测 seed1234 / seed42 / rate 三个 take 的语速（VAD 首尾口径，与 gate 的 B 一致）
  选 |log(rate/target)| 最小的
"""
import sys, os, re, json
sys.path.insert(0, "D:/py_libs"); sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))

def rate_of(path, w):
    if not os.path.exists(path):
        return None, None
    x, sr = sf.read(path, dtype="float32", always_2d=True); x = x.mean(1)
    db, nfl, hop = FP.frame_db(x, sr)
    if len(db) == 0: return None, None
    on = db > (np.percentile(db, 90) - 25.0)
    idx = np.where(on)[0]
    if len(idx) < 5: return None, None
    eff = float(idx[-1] - idx[0] + 1) * hop / sr
    if eff < 0.4: return None, None
    return w / eff * 60, len(x) / sr

g = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]
rows = {r["uid"]: r for r in g["rows"]}
by = {}
for r in g["rows"]:
    if r["pid"] is not None:
        by.setdefault(r["pid"], []).append(r)

SEEDS = ["1234", "42", "rate"]
out = []
for uid in g["culprits"]:
    r = rows[uid]
    grp = sorted(by[r["pid"]], key=lambda r: r["uid"])
    i = [k for k, x in enumerate(grp) if x["uid"] == uid][0]
    nb = []
    if i > 0: nb.append(grp[i - 1]["rate_B"])
    if i + 1 < len(grp): nb.append(grp[i + 1]["rate_B"])
    target = float(np.median(nb)) if nb else float(r["rate_B"])
    w = nwords(S[uid]["text"])
    cand = {}
    for s in SEEDS:
        p = os.path.join("_mt_raw_s" + s, uid + ".wav")
        rate, dur = rate_of(p, w)
        if rate:
            cand[s] = round(rate, 1)
    cur = r["rate_B"]
    best = min(cand.items(), key=lambda kv: abs(np.log(kv[1] / target))) if cand else (None, None)
    out.append(dict(uid=uid, pid=r["pid"], w=w, target=round(target, 1),
                    cur_seed=(S[uid].get("pick") or {}).get("seed"),
                    cur=round(cur, 1),
                    cur_dev=round(float(abs(np.log(cur / target))), 3),
                    cand=cand,
                    best=best[0], best_rate=best[1],
                    best_dev=round(float(abs(np.log(best[1] / target))), 3) if best[1] else None,
                    gain_x=round(max(cur, best[1] or cur) / min(cur, best[1] or cur), 2) if best[1] else 1.0,
                    text=S[uid]["text"][:64]))

print("%-7s %4s %6s %6s %-6s %6s %6s %-6s %6s %6s"
      % ("uid", "词", "目标", "当前", "seed", "偏差", "最佳", "seed", "偏差", "改善"))
fixed = need = 0
for o in sorted(out, key=lambda o: -o["cur_dev"]):
    bd = o["best_dev"] if o["best_dev"] is not None else 9
    ok = bd < 0.10
    fixed += ok; need += not ok
    print("%-7s %4d %6.0f %6.0f %-6s %6.2f %6.0f %-6s %6.2f %6s"
          % (o["uid"], o["w"], o["target"], o["cur"], str(o["cur_seed"]),
             o["cur_dev"], o["best_rate"] or 0, str(o["best"]),
             bd if o["best_dev"] is not None else 9, "✓" if ok else "✗"))

print("\n现有 take 就能解决（偏差<0.10，即 ±10%%）：%d 条" % fixed)
print("仍需新生成：%d 条 → %s" % (need, [o["uid"] for o in out
      if (o["best_dev"] if o["best_dev"] is not None else 9) >= 0.10]))
json.dump(out, open("_rdr_takes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
