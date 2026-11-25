# -*- coding: utf-8 -*-
"""全库零点分布扫描：谁被写进了绝对零（人声不可能有）。"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf


def scan(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    z = np.flatnonzero(y == 0.0)
    if not len(z):
        return dict(runs=0, ms=0.0, frac=0.0, longest=0.0, head=0.0, tail=0.0)
    brk = np.flatnonzero(np.diff(z) != 1) + 1
    runs = np.split(z, brk)
    lens = np.array([len(r) for r in runs])
    ge = lens[lens / sr >= 0.010]
    # 首尾零段
    head = lens[0] / sr * 1000 if z[0] == 0 else 0.0
    tail = lens[-1] / sr * 1000 if z[-1] == len(y) - 1 else 0.0
    return dict(runs=int(len(ge)), ms=round(float(len(z) / sr * 1000), 1),
                frac=round(float(len(z) / len(y)), 4),
                longest=round(float(lens.max() / sr * 1000), 1),
                head=round(head, 1), tail=round(tail, 1))


def main():
    d = sys.argv[1]
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
        out[os.path.basename(p)[:-4]] = scan(p)
    bad = {k: v for k, v in out.items() if v["runs"] > 0}
    print("共 %d 条，含 >=10ms 零段 %d 条" % (len(out), len(bad)))
    tot = sum(v["ms"] for v in out.values()) / 1000
    print("零采样总时长 %.1f s" % tot)
    rows = sorted(out.items(), key=lambda kv: -kv[1]["ms"])
    print("\n%-10s %5s %8s %7s %8s %7s %7s" % ("id", "段数", "总ms", "占比", "最长ms", "头ms", "尾ms"))
    for k, v in rows[:25]:
        print("%-10s %5d %8.1f %7.3f %8.1f %7.1f %7.1f" %
              (k, v["runs"], v["ms"], v["frac"], v["longest"], v["head"], v["tail"]))
    json.dump(out, open("_scan_zero_%s.json" % os.path.basename(d.rstrip("/")), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
