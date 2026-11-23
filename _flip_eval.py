# -*- coding: utf-8 -*-
"""_flip_eval.py —— 在 189 条基准上评估「窗级角色归属翻转」当主判据的 TPR/FPR。

对照 sep：sep 在同批上的表现是 POS 77.5% / NEG_real 6.7% / NEG_emo 38.5%。
"""
import json, os, sys, collections
import numpy as np
sys.path.insert(0, "G:/_setup")
import gate_intra as GI

BENCH = "G:/_setup/_mutbench"
CACHE = os.path.join(BENCH, "emb", "r34")
idx = json.load(open(os.path.join(BENCH, "index.json"), encoding="utf-8"))
refs = GI._role_refs()
roles = sorted(refs)


def top1(e):
    sc = sorted(((w, float(np.max(V @ e))) for w, V in refs.items()), key=lambda x: -x[1])
    return sc[0][0], sc[0][1], sc[1][1]


def eval_item(sid, k=2, mg=0.05):
    z = np.load(os.path.join(CACHE, sid + ".npz"))
    cs, E = z["centers"], z["embs"]
    n = len(E)
    best = None
    for i in range(k, n - k + 1):
        L = GI.nrm(E[i - k:i].mean(0))
        R = GI.nrm(E[i:i + k].mean(0))
        a, sa, sa2 = top1(L)
        b, sb, sb2 = top1(R)
        if a == b:
            continue
        m = min(sa - sa2, sb - sb2)
        if m >= mg and (best is None or m > best[0]):
            best = (m, (cs[i - 1] + cs[i]) / 2, a, b)
    return best


res = {}
for it in idx:
    p = os.path.join(CACHE, it["sid"] + ".npz")
    if not os.path.exists(p):
        continue
    res[it["sid"]] = eval_item(it["sid"])

rows = []
for it in idx:
    sid = it["sid"]
    if sid not in res:
        continue
    b = res[sid]
    rows.append(dict(sid=sid, kind=it["kind"], hit=b is not None,
                     margin=(round(b[0], 3) if b else None),
                     pos=(round(b[1], 2) if b else None),
                     cut=it.get("cut")))

print("评估 %d 条" % len(rows))
for kind in ("POS_hard", "POS_soft", "NEG_emo", "NEG_real"):
    g = [r for r in rows if r["kind"] == kind]
    h = sum(1 for r in g if r["hit"])
    print("  %-9s n=%3d hit=%3d = %5.1f%%" % (kind, len(g), h, 100.0 * h / max(1, len(g))))
pos = [r for r in rows if r["kind"].startswith("POS")]
neg = [r for r in rows if r["kind"].startswith("NEG")]
print("  合计 POS %.1f%% | NEG %.1f%%" % (
    100.0 * sum(r["hit"] for r in pos) / max(1, len(pos)),
    100.0 * sum(r["hit"] for r in neg) / max(1, len(neg))))
loc = [abs(r["pos"] - r["cut"]) for r in pos if r["hit"] and r["pos"] and r["cut"]]
if loc:
    print("  定位 MAE %.2fs | ≤0.75s 命中 %.0f%%" % (
        float(np.mean(loc)), 100.0 * sum(1 for x in loc if x <= 0.75) / len(loc)))
json.dump(rows, open("G:/_setup/_flip_eval.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
