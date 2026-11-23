# -*- coding: utf-8 -*-
"""_mut_real.py —— 把校准好的突变检测器（r34 + sep7）跑到真实 239 条对白上。

与旧工具（`_segcheck_dlg.json`：CAM++ + 静音切段 + 0.55 绝对阈值）逐条对比：
  新增检出 / 重合 / 旧有新无。
输出 `_mut_dlg.json`。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
from _mut_all import M, to16, fbank, score_sep, score_silence

PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
AUD = "G:/_setup/_audio_ch123/out"
OUT = "G:/_setup/_mut_dlg.json"
CACHE = "G:/_setup/_mutcache_real"
WIN, HOP, MIN_WIN = 1.5, 0.25, 0.60
# 分 k 阈值：基准 NEG_real（真实整句，无拼接）p95 校准，FPR≈5%
#   k=7 需 ≥18 窗（≈5.8s）/ k=5 需 ≥14 窗（≈4.8s）/ k=3 需 ≥10 窗（≈3.8s）
K_THR = {7: 0.605, 5: 0.701, 3: 0.791}


def pick_k(n):
    for k in (7, 5, 3):
        if n >= 2 * k + 4:
            return k
    return None


def windows(m, a, feats):
    dur = len(a) / 16000
    cs, es = [], []
    t = 0.0
    T = feats.shape[0]
    while t + WIN <= dur + 1e-6:
        s, e = int(t * 100), min(int((t + WIN) * 100), T)
        if e - s < MIN_WIN * 100:
            break
        cs.append(t + WIN / 2)
        es.append(m.emb_f(feats[s:e]))
        t += HOP
    return np.array(cs), (np.stack(es) if es else np.zeros((0, 256)))


def main():
    os.makedirs(CACHE, exist_ok=True)
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    m = M("r34")
    rows = []
    for k, (i, o) in enumerate(sorted(plan.items()), 1):
        f = os.path.join(AUD, i + ".wav")
        if not os.path.exists(f):
            continue
        cp = os.path.join(CACHE, i + ".npz")
        if os.path.exists(cp):
            z = np.load(cp); cs, E = z["centers"], z["embs"]
        else:
            a = to16(f)
            feats = fbank(a, m.cmn)
            cs, E = windows(m, a, feats)
            np.savez(cp, centers=cs, embs=E)
        k = pick_k(len(E))
        if k is None:
            rows.append({"id": i, "who": o["who"], "emo": o["emo"], "voice": o["voice"],
                         "score": None, "pos": None, "n": len(E), "k": None,
                         "dur": round(len(to16(f)) / 16000, 2), "verdict": "unmeasurable"})
            continue
        s, p = score_sep(cs, E, k, 0.25)
        rows.append({"id": i, "who": o["who"], "emo": o["emo"], "voice": o["voice"],
                     "score": round(float(s), 3) if s is not None else None,
                     "pos": round(p, 2) if p else None, "n": len(E), "k": k,
                     "thr": K_THR[k],
                     "dur": round(len(to16(f)) / 16000, 2),
                     "verdict": ("SUSPECT" if (s is not None and s >= K_THR[k]) else "ok")})
        if k % 60 == 0:
            print("  %d/%d" % (k, len(plan)), flush=True)

    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    meas = [r for r in rows if r["score"] is not None]
    sus = [r for r in meas if r["verdict"] == "SUSPECT"]
    import collections
    print("可测 %d / %d (%.0f%%) | SUSPECT %d | 用 k 分布 %s"
          % (len(meas), len(rows), len(meas) / len(rows) * 100, len(sus),
             dict(collections.Counter(r["k"] for r in meas))))

    # 与旧工具对比
    try:
        old = {x["id"]: x for x in json.load(open("G:/_setup/_segcheck_dlg.json", encoding="utf-8"))}
    except Exception:
        old = {}
    oldc = {i for i, x in old.items() if x.get("min_sim") is not None
            and x["min_sim"] < 0.55 and x.get("f0_span", 0) > 40}
    newc = {r["id"] for r in sus}
    print("旧工具候选 %d 条 | 新工具 %d 条 | 重合 %d" % (len(oldc), len(newc), len(oldc & newc)))
    print("  新检出（旧漏）:", sorted(newc - oldc))
    print("  旧有新无:", sorted(oldc - newc))
    print("  c2_0217（已知真突变）:", "新工具 %s score %.2f" % (
        "检出" if "c2_0217" in newc else "漏", next((r["score"] for r in rows if r["id"] == "c2_0217" and r["score"]), 0)))


if __name__ == "__main__":
    main()
