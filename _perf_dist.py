# -*- coding: utf-8 -*-
"""整段 F0 分布对比（不依赖词边界，稳健）。

    G:/Python310/python.exe _perf_dist.py MP_ P_w_neg,P_w_pos,P_whole,P_mix

输出：中位 F0、p5/p25/p75/p95、F0 标准差（半音）、浊音比例。
若 pitch 标签生效，对应分位会明显移动。
"""
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
BASE = D + "MKT_L_plain.wav"


def stats(path):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=400.0, time_step=0.01)
    v = pit.selected_array["frequency"]
    v = v[v > 0]
    if v.size < 10:
        return None
    st = 12 * np.log2(v / 100.0)          # 以 100Hz 为参考转半音，便于比离散度
    return dict(n=int(v.size),
                med=float(np.median(v)),
                p5=float(np.percentile(v, 5)),
                p25=float(np.percentile(v, 25)),
                p75=float(np.percentile(v, 75)),
                p95=float(np.percentile(v, 95)),
                sd_st=float(np.std(st)))


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = [v for v in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if v]

    b = stats(BASE)
    print("基线 MKT_L_plain  中位 %.1f Hz  p5 %.1f  p95 %.1f  离散 %.2f 半音  浊音帧 %d"
          % (b["med"], b["p5"], b["p95"], b["sd_st"], b["n"]))
    print()
    print("%-10s %8s %8s %8s %8s %9s %8s" %
          ("变体", "中位Hz", "Δ半音", "p5Hz", "p95Hz", "离散半音", "浊音帧"))
    print("-" * 68)
    for v in variants:
        p = D + prefix + v + ".wav"
        if not os.path.exists(p):
            print("%-10s MISSING" % v)
            continue
        s = stats(p)
        if not s:
            print("%-10s 浊音不足" % v)
            continue
        d = 12 * np.log2(s["med"] / b["med"])
        print("%-10s %8.1f %+8.2f %8.1f %8.1f %9.2f %8d"
              % (v, s["med"], d, s["p5"], s["p95"], s["sd_st"], s["n"]))


if __name__ == "__main__":
    main()
