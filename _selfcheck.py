# -*- coding: utf-8 -*-
"""交付版自检：全零采样、句内最长静音、voiced 电平跨度。"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _shorten_pause import voiced_runs
from narr_gate_phys import voiced_db

D = "G:/_setup/_audio_ch123/out_deliver"
zero_files = 0
zero_total = 0.0
maxgap = []
dbs = []
for f in sorted(glob.glob(os.path.join(D, "*.wav"))):
    y, sr = sf.read(f, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    z = (y == 0)
    if z.any():
        zero_files += 1
        zero_total += z.sum() / sr
    r = voiced_runs(y, sr)
    g = [(r[i + 1][0] - r[i][1]) / sr for i in range(len(r) - 1)]
    maxgap.append((max(g) if g else 0.0, os.path.basename(f)[:-4]))
    dbs.append(voiced_db(y, sr)[0])

maxgap.sort(reverse=True)
print("文件数 %d" % len(dbs))
print("仍有全零采样: %d 条，累计 %.2fs" % (zero_files, zero_total))
print("句内最长静音 top5: %s" % [(round(a, 2), b) for a, b in maxgap[:5]])
print(">0.45s 的条数: %d" % sum(1 for a, _ in maxgap if a > 0.45))
print("voiced 电平 %.2f ~ %.2f dBFS（跨度 %.2f）" % (min(dbs), max(dbs), max(dbs) - min(dbs)))
