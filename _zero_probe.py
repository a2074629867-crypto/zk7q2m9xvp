# -*- coding: utf-8 -*-
"""测交付版里最长的「连续全零」时长（听觉上的真空），而不是零采样总数。"""
import glob
import os

import numpy as np
import soundfile as sf

D = "G:/_setup/_audio_ch123/out_deliver"
rows = []
for f in sorted(glob.glob(os.path.join(D, "*.wav"))):
    y, sr = sf.read(f, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    z = (y == 0).astype(np.int8)
    d = np.diff(np.concatenate([[0], z, [0]]))
    s = np.where(d == 1)[0]
    e = np.where(d == -1)[0]
    longest = (e - s).max() / sr if len(s) else 0.0
    rows.append((round(float(longest), 3), round(float(z.sum()) / sr, 3),
                 os.path.basename(f)[:-4]))
rows.sort(reverse=True)
print("最长连续全零 top8:")
for a, b, n in rows[:8]:
    print("   %-9s 最长 %.3fs  累计 %.3fs" % (n, a, b))
print("最长连续全零 >0.10s 的条数: %d" % sum(1 for a, _, _ in rows if a > 0.10))
print("最长连续全零 >0.05s 的条数: %d" % sum(1 for a, _, _ in rows if a > 0.05))
