# -*- coding: utf-8 -*-
"""拼接爆音检测：相邻采样差分超过阈值即可疑（48k，语音本身 |d| 很少 >0.3）。"""
import sys
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf
for f in ["_chap_ch1_v4.wav", "_chap_ch1_v4b.wav"]:
    x, sr = sf.read(f, dtype="float32", always_2d=True)
    x = x.mean(1)
    d = np.abs(np.diff(x))
    p = np.percentile(d, [99, 99.9, 99.99, 99.999])
    print("%-22s p99/99.9/99.99/99.999 = %s  max %.3f  超0.3的点 %d" %
          (f, [round(float(v), 4) for v in p], float(d.max()), int((d > 0.3).sum())))
