# -*- coding: utf-8 -*-
"""滑动窗 F0 差分：找变体相对基线 F0 偏移最大的局部区间。

不依赖词边界，直接回答「某处是否真的降/升了调」。

    G:/Python310/python.exe _perf_diff.py MP_ P_w_neg,P_w_pos,P_whole,P_mix

方法：两段音频时长归一化到同一时间轴，逐帧取 F0（对数域），
滑窗（默认 0.40s）算窗口内中位差，输出 |差| 最大的 3 个窗口。
"""
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
BASE = D + "MKT_L_plain.wav"
WIN = 0.40


def f0_track(path):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=400.0, time_step=0.01)
    return pit.xs(), pit.selected_array["frequency"], snd.get_total_duration()


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = [v for v in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if v]

    bt, bf, bd = f0_track(BASE)
    # 基线帧时间归一化到 [0,1]，便于与不同时长的变体对齐
    bn = bt / bd

    for v in variants:
        p = D + prefix + v + ".wav"
        if not os.path.exists(p):
            print("%-10s MISSING" % v)
            continue
        vt, vf, vd = f0_track(p)
        vn = vt / vd

        # 统一网格
        grid = np.arange(0.0, 1.0, 0.01)
        bsel = np.interp(grid, bn, bf, left=0, right=0)
        vsel = np.interp(grid, vn, vf, left=0, right=0)
        ok = (bsel > 0) & (vsel > 0)
        if ok.sum() < 20:
            print("%-10s 有效帧不足" % v)
            continue
        diff = np.full(grid.shape, np.nan)
        diff[ok] = 12 * np.log2(vsel[ok] / bsel[ok])

        w = int(WIN / 0.01)
        best = []
        for i in range(0, len(grid) - w):
            seg = diff[i:i + w]
            seg = seg[~np.isnan(seg)]
            if seg.size < w * 0.4:
                continue
            best.append((abs(float(np.median(seg))), float(np.median(seg)),
                         grid[i], grid[i + w]))
        best.sort(reverse=True)
        print("=== %s  总长 %.2fs (基线 %.2fs, %+.1f%%)"
              % (v, vd, bd, 100 * (vd / bd - 1)))
        for _, med, a, b in best[:3]:
            print("    窗 %.2f–%.2f 归一化  中位差 %+.2f 半音  (绝对位置 %.1f–%.1fs)"
                  % (a, b, med, a * vd, b * vd))
        # 全局
        allm = diff[~np.isnan(diff)]
        print("    全程中位差 %+.2f 半音 | 帧差标准差 %.2f | 极值 %+.2f / %+.2f"
              % (float(np.median(allm)), float(np.std(allm)),
                 float(np.percentile(allm, 2)), float(np.percentile(allm, 98))))
        print()


if __name__ == "__main__":
    main()
