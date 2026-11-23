# -*- coding: utf-8 -*-
"""浊音帧序列对齐的 F0 差分。

文本相同 ⇒ 两段音频的浊音帧序列大致一一对应，按索引对齐后逐帧算半音差，
再做滑动中位平滑，找偏移最大的区段。避开清音帧与插值误差。

    G:/Python310/python.exe _perf_seq.py MP_ P_w_neg,P_w_pos,P_whole,P_mix
"""
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
BASE = D + "MKT_L_plain.wav"
WIN = 40          # 浊音帧窗口（帧步长 10ms → 约 0.4s 浊音）


def voiced(path):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=400.0, time_step=0.01)
    xs = pit.xs()
    f = pit.selected_array["frequency"]
    m = f > 0
    return xs[m], f[m], snd.get_total_duration()


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = [v for v in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if v]

    bt, bf, bd = voiced(BASE)
    print("基线浊音帧 %d / 时长 %.2fs" % (len(bf), bd))
    print()

    for v in variants:
        p = D + prefix + v + ".wav"
        if not os.path.exists(p):
            print("%-10s MISSING" % v)
            continue
        vt, vf, vd = voiced(p)
        n = min(len(bf), len(vf))
        if n < WIN * 2:
            print("%-10s 浊音帧太少 (%d vs %d)" % (v, len(vf), len(bf)))
            continue

        # 按索引对齐（两段都念同一文本，浊音帧数应接近）
        ratio = 12 * np.log2(vf[:n] / bf[:n])
        # 滑动中位
        med = np.array([np.median(ratio[max(0, i - WIN // 2):i + WIN // 2 + 1])
                        for i in range(n)])
        k = int(np.argmax(np.abs(med)))

        # 映射回时间（用基线时间轴）
        t_peak = bt[min(k, len(bt) - 1)]

        print("=== %s  浊音帧 %d (基线 %d) | 总长 %.2fs (%+.1f%%)"
              % (v, len(vf), len(bf), vd, 100 * (vd / bd - 1)))
        print("    帧索引 %d → 基线时刻 %.2fs | 窗口内中位差 %+.2f 半音"
              % (k, t_peak, med[k]))
        print("    全程 中位 %+.2f | 标准差 %.2f | p2 %+.2f | p98 %+.2f | 极值 %+.2f"
              % (float(np.median(ratio)), float(np.std(ratio)),
                 float(np.percentile(ratio, 2)), float(np.percentile(ratio, 98)),
                 float(ratio[np.argmax(np.abs(ratio))])))
        print("    偏移>3半音的帧: %d / %d (%.1f%%)"
              % (int((np.abs(ratio) > 3).sum()), n,
                 100 * (np.abs(ratio) > 3).mean()))
        print()


if __name__ == "__main__":
    main()
