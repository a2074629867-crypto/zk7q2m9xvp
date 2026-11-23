# -*- coding: utf-8 -*-
"""单元间电平一致性（红线：voiced RMS 跨度 ≤1dB）。"""
import sys, glob, os
sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

def vrms(x, sr):
    db, _, hop = FP.frame_db(x, sr)
    thr = np.percentile(db, 90) - 25.0
    on = db > thr
    if on.sum() < 3:
        return np.nan
    seg = []
    for i in np.where(on)[0]:
        a = i * hop; b = min(len(x), a + hop)
        seg.append(x[a:b])
    y = np.concatenate(seg).astype(np.float64)
    return 20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12)

for d in ["_mt_final_raw_ch1", "_mt_final_raw_trim"]:
    vs = []
    for p in sorted(glob.glob(d + "/*.wav")):
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        vs.append((os.path.basename(p)[:-4], vrms(x.mean(1), sr)))
    a = np.array([v for _, v in vs if not np.isnan(v)])
    print("%-24s n=%d  p50 %.1f  跨度 %.2f dB  (%.1f ~ %.1f)" %
          (d, len(a), np.median(a), a.max() - a.min(), a.min(), a.max()))
