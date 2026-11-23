# -*- coding: utf-8 -*-
"""短源 edit 实验的第二步（G:/Python310）：F0 对比。

    G:/Python310/python.exe _es_f0.py [目标词]

读 _es_ts.json。同时给出：
  1. 整段 F0 分布（整段 pitch 标签是否生效）
  2. 目标词 F0（词级标签是否生效）—— 若 ASR 词窗 < 0.12s 则用 ±0.12s 扩窗
"""
import json
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
TS = "G:/_setup/_es_ts.json"


def pitch_obj(path):
    snd = parselmouth.Sound(path)
    return snd, snd.to_pitch(pitch_floor=50.0, pitch_ceiling=400.0, time_step=0.01)


def dist(pit):
    f = pit.selected_array["frequency"]
    f = f[f > 0]
    if f.size < 10:
        return None
    return dict(med=float(np.median(f)), p5=float(np.percentile(f, 5)),
                p95=float(np.percentile(f, 95)), n=int(f.size))


def word_f0(pit, t0, t1, pad=0.12):
    xs = pit.xs()
    f = pit.selected_array["frequency"]
    a, b = t0 - pad, t1 + pad
    m = (xs >= a) & (xs <= b) & (f > 0)
    if m.sum() < 3:
        return None, 0
    return float(np.median(f[m])), int(m.sum())


def find(ws, target):
    for w, a, b in ws:
        if w.lower().strip(".,;:!?\"'") == target:
            return a, b
    return None


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "hair"
    d = json.load(open(TS, encoding="utf-8"))
    if "BASE" not in d:
        print("no BASE")
        return

    _, bp = pitch_obj(D + "ES_src.wav")
    bd = dist(bp)
    pos = find(d["BASE"]["words"], target)
    bf, bn = word_f0(bp, pos[0], pos[1]) if pos else (None, 0)

    print("基线 ES_src.wav  时长 %.2fs | 整段中位 %.1f Hz (p5 %.1f / p95 %.1f)"
          % (d["BASE"]["dur"], bd["med"], bd["p5"], bd["p95"]))
    if bf:
        print("   %s 词窗 %.2f-%.2f → F0 %.1f Hz (%d 帧)"
              % (target, pos[0], pos[1], bf, bn))
    print()
    print("%-10s %7s %6s %9s %8s %8s %10s" %
          ("变体", "时长", "词数", "整段中位", "Δ半音", "p5/p95", "目标词F0"))
    print("-" * 74)

    for name, info in d.items():
        if name == "BASE":
            continue
        p = D + "MES_" + name + ".wav"
        if not os.path.exists(p):
            print("%-10s MISSING" % name)
            continue
        _, vp = pitch_obj(p)
        vd = dist(vp)
        pos2 = find(info["words"], target)
        vf, vn = word_f0(vp, pos2[0], pos2[1]) if pos2 else (None, 0)
        semi = 12 * np.log2(vd["med"] / bd["med"])
        wf = ("%.1f (%+.1f半)" % (vf, 12 * np.log2(vf / bf))) if (vf and bf) else "-"
        print("%-10s %6.2fs %4d/%-2d %8.1f %+8.2f %5.0f/%-4.0f %10s"
              % (name, info["dur"], len(info["words"]),
                 len(d["BASE"]["words"]), vd["med"], semi,
                 vd["p5"], vd["p95"], wf))


if __name__ == "__main__":
    main()
