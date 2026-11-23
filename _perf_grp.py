# -*- coding: utf-8 -*-
"""按「词组」对齐比较 F0：用 ASR 词级时间戳当锚点，每 K 个词一组。

单词窗太短（80ms 粒度）测不准 F0；把相邻 K 个词合成一组，窗长够、锚点仍可靠。

    G:/Python310/python.exe _perf_grp.py MP_ P_w_neg,P_w_pos,P_whole,P_mix [K]

读 _perf_ts.json（_perf_ts.py 生成）。输出每组的中位 F0 差（半音），
并标出偏移最大的组，以及它对应的原文片段。
"""
import json
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
TS = "G:/_setup/_perf_ts.json"


def f0_med(path, t0, t1):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=400.0, time_step=0.01)
    xs = pit.xs()
    f = pit.selected_array["frequency"]
    m = (xs >= t0) & (xs <= t1) & (f > 0)
    if m.sum() < 3:
        return None
    return float(np.median(f[m]))


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = [v for v in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if v]
    K = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    d = json.load(open(TS, encoding="utf-8"))
    if "BASE" not in d:
        print("no BASE")
        return
    bw = d["BASE"]["words"]
    n = len(bw)

    # 基线分组 F0
    base_grp = []
    for i in range(0, n, K):
        seg = bw[i:i + K]
        if not seg:
            continue
        t0, t1 = seg[0][1], seg[-1][2]
        base_grp.append((i, t0, t1, f0_med(D + "MKT_L_plain.wav", t0, t1),
                         " ".join(w[0] for w in seg)))
    print("基线 %d 词 → %d 组 (K=%d)" % (n, len(base_grp), K))
    print()

    for v in variants:
        if v not in d:
            print("%-10s 无时间戳" % v)
            continue
        vw = d[v]["words"]
        rows = []
        for gi, (i, t0, t1, bf, txt) in enumerate(base_grp):
            seg = vw[i:i + K]
            if not seg or bf is None:
                continue
            vf = f0_med(D + prefix + v + ".wav", seg[0][1], seg[-1][2])
            if vf is None:
                continue
            rows.append((gi, 12 * np.log2(vf / bf), bf, vf, txt))
        if not rows:
            print("%-10s 无可比组" % v)
            continue
        diffs = np.array([r[1] for r in rows])
        print("=== %s  可比组 %d | 全程中位差 %+.2f 半音 | 标准差 %.2f | |差|>3 的组 %d (%.0f%%)"
              % (v, len(rows), float(np.median(diffs)), float(np.std(diffs)),
                 int((np.abs(diffs) > 3).sum()), 100 * (np.abs(diffs) > 3).mean()))
        top = sorted(rows, key=lambda r: -abs(r[1]))[:3]
        for gi, dv, bf, vf, txt in top:
            print("    组%2d  %+.2f 半音 (%.0f→%.0f Hz)  「%s」"
                  % (gi, dv, bf, vf, txt[:60]))
        print()


if __name__ == "__main__":
    main()
