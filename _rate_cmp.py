# -*- coding: utf-8 -*-
"""两种语速口径并列对比：含停顿（wpm_span）vs 去停顿（articulation）。

为什么必须并列：常用基准「正常对白 152~190 wpm」是**含停顿**的口径；
articulation 天生偏高（英文约 200~260）。拿 107 或 252 直接比 152~190 都是错的。
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _rate as R


def dist(rows, label):
    A, S = [], []
    for rid, path, text in rows:
        if not os.path.exists(path):
            continue
        r = R.rate(path, text)
        if r["wpm"]:
            A.append(r["wpm"])
        if r["wpm_span"]:
            S.append(r["wpm_span"])
    if not A:
        print("%-22s 无数据" % label)
        return
    print("%-20s n=%3d | 含停顿 中位 %5.0f (p25 %3.0f  p75 %3.0f) | "
          "去停顿 中位 %5.0f (p25 %3.0f  p75 %3.0f)"
          % (label, len(A), np.median(S), np.percentile(S, 25), np.percentile(S, 75),
             np.median(A), np.percentile(A, 25), np.percentile(A, 75)))


def main():
    plan = {}
    with open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                plan[d["id"]] = d

    rows = [(i, os.path.join(HERE, "_audio_ch123/out/%s.wav" % i), plan[i]["text"])
            for i in plan]
    dist(rows, "全库 现成品")

    fill = [x for x in open(os.path.join(HERE, "_notxt66_fill_ids.txt")).read().split(",") if x]
    dist([(i, os.path.join(HERE, "_audio_ch123/out/%s.wav" % i), plan[i]["text"]) for i in fill],
         "已回填 21 条")

    d = os.path.join(HERE, "_sweep", "notxt66_trim")
    ids = sorted({f.split("__")[0] for f in os.listdir(d) if f.endswith(".wav")} & set(plan))
    dist([(i, os.path.join(d, "%s__s42.wav" % i), plan[i]["text"]) for i in ids], "noref 新版 66 条")

    ref = os.path.join(HERE, "_ref9", "Joseph_normal.wav")
    if os.path.exists(ref):
        r = R.rate(ref, words=23)     # 词数取它自己的 ASR 结果（标注文本已证实是错的）
        print("%-20s        | 含停顿 中位 %5.0f | 去停顿 中位 %5.0f（词数用 ASR，偏低，仅供参考）"
              % ("电影原声参考", r["wpm_span"] or 0, r["wpm"] or 0))

    print("\n基准：正常对白「含停顿」152~190 wpm；「去停顿」约 200~260 wpm。")


if __name__ == "__main__":
    main()
