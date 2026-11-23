# -*- coding: utf-8 -*-
"""步数稳定性评估：同句、同步数、三个 seed，看目标词名次的离散度。"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
from _step_eval import feats, norm, TARGET, TEXTS  # noqa: E402

ROOT = "G:/_setup"
VAR = os.path.join(ROOT, "_step_var")
TGT = TARGET["n0112"]


def main():
    files = sorted(glob.glob(os.path.join(VAR, "*.wav")))
    raw = json.load(open(os.path.join(ROOT, "_step_var_words.json"), encoding="utf-8"))
    groups = {}
    for p in files:
        fn = os.path.basename(p)
        m = re.match(r"(\w+)_s(\d+)_seed(\d+)\.wav$", fn)
        if not m:
            continue
        v = raw.get(fn)
        if not v or "words" not in v:
            print("缺 ASR:", fn)
            continue
        ft = feats(p, v["words"])
        if not ft:
            continue
        rk = None
        tf0 = None
        for w in ft["words"]:
            if norm(w["w"]).startswith(norm(TGT)[:6]):
                rk = 1 + sum(1 for x in ft["words"] if x["prom"] > w["prom"])
                tf0 = w["f0_st"]
                break
        groups.setdefault(int(m.group(2)), []).append(
            dict(seed=int(m.group(3)), rank=rk, n=ft["n"], top=ft["top_w"],
                 pos=ft["pos"], f0=tf0, span=ft["span"], dur=ft["dur"]))

    print("\n%s  |  %s" % ("N0112 稳定性", TEXTS["n0112"]))
    for steps in sorted(groups):
        g = sorted(groups[steps], key=lambda x: x["seed"])
        ranks = [x["rank"] for x in g]
        tops = [x["top"] for x in g]
        print("\n=== %d 步 ===" % steps)
        for x in g:
            print("  seed %-6d 目标名次 %s/%d  目标F0 %+.2f  top1=%-12s pos %.3f  F0跨度 %.1f  时长 %.2f"
                  % (x["seed"], x["rank"], x["n"], x["f0"], x["top"], x["pos"], x["span"], x["dur"]))
        print("  名次序列 %s | 极差 %d | 均值 %.2f | 进前三 %d/3 | top1 同词 %d/3"
              % (ranks, max(ranks) - min(ranks), float(np.mean(ranks)),
                 sum(1 for r in ranks if r <= 3), len(set(tops)) == 1 and 3 or
                 sum(1 for t in tops if tops.count(t) >= 2)))

    print("\n" + "=" * 70)
    print("对照：同一句在 3 个 seed 下的名次极差，越大 = 越不稳定")


if __name__ == "__main__":
    main()
