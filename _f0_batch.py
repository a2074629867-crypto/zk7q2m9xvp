# -*- coding: utf-8 -*-
"""批量测一批 wav 的中位 F0 / 时长，用于挑音色。
用法: G:/Python310/python.exe _f0_batch.py <目录或文件...>
"""
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf


def read_wav(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def f0_track(a, sr, fmin=60, fmax=400):
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    return pitch.xs(), pitch.selected_array["frequency"]


def main():
    targets = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            for f in sorted(os.listdir(arg)):
                if f.lower().endswith(".wav"):
                    targets.append(os.path.join(arg, f))
        elif os.path.exists(arg):
            targets.append(arg)

    rows = []
    for p in targets:
        try:
            a, sr = read_wav(p)
        except Exception as e:
            print("skip", p, e)
            continue
        dur = len(a) / sr
        t, f = f0_track(a, sr)
        m = f > 0
        if not m.any():
            rows.append((os.path.basename(p), dur, None, None))
            continue
        med = float(np.median(f[m]))
        p10 = float(np.percentile(f[m], 10))
        p90 = float(np.percentile(f[m], 90))
        rows.append((os.path.basename(p), dur, med, (p10, p90)))

    rows.sort(key=lambda r: (r[2] is None, r[2] or 999))
    print("%-26s %7s %8s %8s %8s %s" % ("文件", "时长", "中位F0", "P10", "P90", "判定"))
    for name, dur, med, rg in rows:
        if med is None:
            print("%-26s %6.2fs %8s %8s %8s %s" % (name, dur, "-", "-", "-", "无声"))
            continue
        tag = "男低" if med < 120 else ("男中" if med < 165 else ("少年" if med < 210 else "偏高/女"))
        print("%-26s %6.2fs %7.1f %8.1f %8.1f %s"
              % (name, dur, med, rg[0], rg[1], tag))


if __name__ == "__main__":
    main()
