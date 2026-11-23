# -*- coding: utf-8 -*-
"""第二步（G:/Python310，带 parselmouth）：算目标词 F0 半音偏移 + 词时长。

    G:/Python310/python.exe _perf_f0.py hair,cosmos

读 _perf_ts.json（由 _perf_ts.py 生成）。
"""
import json
import os
import sys

import numpy as np
import parselmouth

D = "G:/_setup/dots_edit2/"
TS = "G:/_setup/_perf_ts.json"


def f0_median(path, t0, t1):
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=500.0, time_step=0.01)
    vals = pit.selected_array["frequency"]
    times = pit.xs()
    m = (times >= t0) & (times <= t1) & (vals > 0)
    if m.sum() < 3:
        return None
    return float(np.median(vals[m]))


def find(ws, target):
    for w, a, b in ws:
        if w.lower().strip(".,;:!?\"'") == target:
            return a, b
    return None


def main():
    targets = (sys.argv[1] if len(sys.argv) > 1 else "hair").split(",")
    targets = [t for t in targets if t]
    d = json.load(open(TS, encoding="utf-8"))
    if "BASE" not in d:
        print("no BASE")
        return

    base = {}
    for t in targets:
        pos = find(d["BASE"]["words"], t)
        if not pos:
            print("基线里找不到", t)
            continue
        f = f0_median(D + "MKT_L_plain.wav", pos[0], pos[1])
        base[t] = dict(f0=f, dur=pos[1] - pos[0])
        print("基线 %-8s F0 %s Hz | 词长 %.2fs"
              % (t, ("%.1f" % f) if f else "-", pos[1] - pos[0]))
    print()

    hdr = "%-10s %7s %6s  " % ("变体", "总长", "词数")
    for t in targets:
        hdr += "%-30s" % t
    print(hdr)
    print("-" * len(hdr))

    for name, info in d.items():
        if name == "BASE":
            continue
        line = "%-10s %6.2fs %4d  " % (name, info["dur"], len(info["words"]))
        for t in targets:
            pos = find(info["words"], t)
            if not pos or t not in base:
                line += "%-30s" % "未找到"
                continue
            f = f0_median(D + "MP_" + name + ".wav", pos[0], pos[1])
            dur = pos[1] - pos[0]
            semi = (12 * np.log2(f / base[t]["f0"])) if (f and base[t]["f0"]) else None
            dr = dur / base[t]["dur"] if base[t]["dur"] else None
            line += "%-30s" % ("%s F0 %.1f 词长%.2f(%+.0f%%)"
                               % (("%+.1f半" % semi) if semi is not None else "半音-",
                                  f or 0, dur, 100 * ((dr or 1) - 1)))
        print(line)


if __name__ == "__main__":
    main()
