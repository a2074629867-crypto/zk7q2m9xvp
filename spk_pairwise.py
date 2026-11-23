#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""比较声纹模型在「两个童声」上的可分性。
用 pipeline 的 pairwise score，算类内 vs 类间分离度。
"""
import os, sys, itertools
import numpy as np

REF = "G:/_setup/castle_fr_ref16"
C = ["1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav"]
H = ["5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav"]
MODEL = os.environ.get("SPK_MODEL", "G:/_setup/models/ms/iic/speech_campplus_sv_zh-cn_16k-common")


def main():
    from modelscope.pipelines import pipeline
    from modelscope.utils.constant import Tasks
    sv = pipeline(task=Tasks.speaker_verification, model=MODEL)
    print("模型", os.path.basename(MODEL), flush=True)

    files = [(f, "C") for f in C] + [(f, "H") for f in H]
    files = [(f, r) for f, r in files if os.path.exists(os.path.join(REF, f))]
    if len(files) < 4:
        print("锚点不足"); return

    intra, inter = [], []
    for (a, ra), (b, rb) in itertools.combinations(files, 2):
        sc = sv([os.path.join(REF, a), os.path.join(REF, b)]).get("score", 0.0)
        (intra if ra == rb else inter).append((float(sc), a, b))

    iv = [x[0] for x in intra]; er = [x[0] for x in inter]
    print("类内 n=%d  min=%.3f 中位=%.3f  max=%.3f" % (len(iv), min(iv), np.median(iv), max(iv)))
    print("类间 n=%d  min=%.3f 中位=%.3f  max=%.3f" % (len(er), min(er), np.median(er), max(er)))
    sep = min(iv) - max(er)
    print("分离度 = %.3f  ->  %s" % (sep, "能分开" if sep > 0 else "分不开"))
    worst = max(inter, key=lambda x: x[0])
    print("最像的跨角色：%s vs %s = %.3f" % (worst[1][:24], worst[2][:24], worst[0]))
    best_in = min(intra, key=lambda x: x[0])
    print("最不像的同角色：%s vs %s = %.3f" % (best_in[1][:24], best_in[2][:24], best_in[0]))


if __name__ == "__main__":
    main()
