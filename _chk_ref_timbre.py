# -*- coding: utf-8 -*-
"""核对 §4.6：11-12 新补档（self-cut）与旧档（castlecues 法语片）是否同一音色。

判据：说话人 embedding 余弦
  baseline  = 旧档内部两两余弦（同一人不同情绪的下限）
  target    = 新档 vs 旧档质心
  若 target 明显低于 baseline 下沿 ⇒ 换人了，不许拿去重生成。
"""
import sys, json, os, itertools
sys.path.insert(0, "G:/_setup")
import numpy as np
from chain_check import SV

LIB = "G:/_setup/_emo_refs_all.json"
lib = json.load(open(LIB, encoding="utf-8"))
m = SV("r34")

def cos(a, b):
    return float(a @ b/ (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

out = {}
for sp in ("Charles", "Thomas"):
    old, new = [], []
    for emo, items in lib[sp].items():
        for it in items:
            src = it.get("src", "castlecues(fr)")
            (new if "self-cut" in src else old).append((emo, it["path"]))
    print("\n=== %s  旧%d条 / 新%d条" % (sp, len(old), len(new)))
    eo = {p: m.embed(p) for _, p in old}
    en = {p: m.embed(p) for _, p in new}
    base = [cos(eo[a], eo[b]) for a, b in itertools.combinations(eo, 2)]
    cen = np.mean([eo[p] for _, p in old], axis=0)
    rec = {"old_pairwise_min": min(base), "old_pairwise_p25": float(np.percentile(base, 25)),
           "old_pairwise_med": float(np.median(base)), "new": []}
    print("  旧档内部 两两余弦: min %.3f  p25 %.3f  中位 %.3f  max %.3f"
          % (min(base), np.percentile(base, 25), np.median(base), max(base)))
    for (emo, p), e in zip(new, [en[p] for _, p in new]):
        c_cen = cos(e, cen)
        c_best = max(cos(e, eo[q]) for q in eo)
        rec["new"].append({"emo": emo, "path": p, "vs_centroid": round(c_cen, 3),
                           "vs_best_old": round(c_best, 3)})
        print("  %-8s vs质心 %.3f   vs最佳旧档 %.3f   %s" % (emo, c_cen, c_best, os.path.basename(p)))
    out[sp] = rec

json.dump(out, open("G:/_setup/_chk_ref_timbre.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n落盘 G:/_setup/_chk_ref_timbre.json")
