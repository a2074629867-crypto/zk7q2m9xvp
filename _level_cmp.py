# -*- coding: utf-8 -*-
"""_level_cmp.py —— 对比两个目录的 voiced RMS 电平（交付口径 −24 dBFS，跨度 ≤1dB）。

voiced 判定用 20ms 帧能量 > p90−20dB（与 _speedlib 一致），只统计有声帧。
用法：G:/Python310/python.exe -u _level_cmp.py _regen_final _pause_fix2
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def voiced_rms(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    hop = int(sr * 0.02)
    n = len(y) // hop
    if n < 5:
        return None
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - 20, -60)
    v = db > thr
    if v.sum() < 5:
        return None
    # 能量平均（不是算术平均 dB）
    return float(10 * np.log10(np.mean(e[v] ** 2) + 1e-20))


def main():
    ids = set(json.load(open(os.path.join(HERE, "_narr_ids716.json"), encoding="utf-8")))
    for d in sys.argv[1:]:
        full = os.path.join(HERE, d)
        if not os.path.isdir(full):
            print(d, "不存在")
            continue
        vals = []
        for p in sorted(glob.glob(full + "/*.wav")):
            if os.path.basename(p)[:-4] not in ids:
                continue
            v = voiced_rms(p)
            if v is not None:
                vals.append(v)
        v = np.array(vals)
        print("%-16s n=%3d  voiced RMS 中位 %.2f dBFS  p5 %.2f  p95 %.2f  跨度 %.2f dB  |偏离−24|>1 的 %d 句"
              % (d, len(v), np.median(v), np.percentile(v, 5), np.percentile(v, 95),
                 np.percentile(v, 95) - np.percentile(v, 5), int((np.abs(v + 24) > 1).sum())))


if __name__ == "__main__":
    main()
