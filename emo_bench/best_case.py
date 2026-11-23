#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""48 条生成矩阵里，每类情绪的最好成绩（全 ref × 全条件）。
回答：现有素材到底能演到什么程度，哪些情绪是硬缺口。"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)

stats = json.load(open(P("out", "ref_stats.json"), encoding="utf-8"))
PRIMARY = {
    "兴奋": ("vox", "a_x_v"),
    "激动反抗": ("vox", "d"),
    "紧张": ("vox", "a_x_nd"),
    "委屈": ("vox", "neg_a"),
    "警惕": ("e2v", "厌恶/disgusted"),
    "平静": ("vox", "v"),
}


def vf(A, V, D, k):
    return {"a": A, "v": V, "d": D, "neg_a": 1 - A, "neg_v": 1 - V, "neg_d": 1 - D,
            "a_x_v": A * V, "a_x_nd": A * (1 - D), "a_x_v_x_d": A * (1 - V) * D,
            "neg_a_neg_v_neg_d": (1 - A) * (1 - V) * (1 - D)}[k]


def pct(v, dist):
    arr = np.array([dist["p10"], dist["p25"], dist["p50"], dist["p75"], dist["p90"]])
    qs = [.10, .25, .50, .75, .90]
    for i in range(1, len(arr)):
        if v <= arr[i]:
            f = (v - arr[i - 1]) / max(1e-9, arr[i] - arr[i - 1])
            return qs[i - 1] + f * (qs[i] - qs[i - 1])
    return .90 + min(.10, (v - arr[-1]) / max(1e-9, arr[-1]) * .3)


gen = {g["path"]: g for g in (json.loads(l) for l in open(P("out", "gen_index.jsonl"), encoding="utf-8"))}
vox = [json.loads(l) for l in open(P("out", "gen_vox_dim.jsonl"), encoding="utf-8")]
e2v = {json.loads(l)["path"]: json.loads(l) for l in open(P("out", "gen_e2v.jsonl"), encoding="utf-8")}

best, allp = {}, {k: [] for k in PRIMARY}
for r in vox:
    g = gen.get(r["path"])
    if not g:
        continue
    sc = r["score"]
    for emo, (src, key) in PRIMARY.items():
        if src == "vox":
            val = vf(sc["arousal"], sc["valence"], sc["dominance"], key)
        else:
            e = e2v.get(r["path"])
            if not e:
                continue
            val = float(e["score"].get(key, 0.0))
        st = stats[emo]["signals"]["%s:%s" % (src, key)]
        p = 100 * pct(val, st["pos"])
        allp[emo].append(p)
        if emo not in best or p > best[emo][0]:
            best[emo] = (p, val, g["pid"], g["cond"], st["threshold_fpr25"], st["threshold"], st["auc"])

print("48 条（8 ref × 6 条件）里每类情绪的最好成绩")
print("%-9s %8s %7s %-10s %-7s %7s %7s %6s" % ("情绪", "最高分位", "判据值", "最佳ref", "条件", "P25线", "AUC", "判定"))
for emo in ["激动反抗", "委屈", "警惕", "紧张", "兴奋", "平静"]:
    p, val, pid, c, t25, t10, auc = best[emo]
    flag = "到位" if val > t25 else ("勉强" if val > t10 else "没演出来")
    print("%-9s %6.0f%%   %6.3f   %-10s %-7s %6.3f  %6.3f  %s" % (emo, p, val, pid, c, t25, auc, flag))

print()
print("分位分布（48 条）")
print("%-9s %6s %6s %6s %6s" % ("情绪", "P25", "中位", "P75", "P90"))
for emo in ["激动反抗", "委屈", "警惕", "紧张", "兴奋", "平静"]:
    a = np.array(allp[emo])
    print("%-9s %6.0f %6.0f %6.0f %6.0f" % (emo, np.percentile(a, 25), np.median(a), np.percentile(a, 75), np.percentile(a, 90)))
