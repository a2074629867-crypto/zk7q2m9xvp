# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, "D:/py_libs"); sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP
MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
x, sr = sf.read(MASTER, dtype="float32", always_2d=True); x = x.mean(1)
db, _, hop = FP.frame_db(x, sr)
on = db > (np.percentile(db, 90) - 25.0)
voiced = float(on.sum()) * hop / sr; tot = len(x)/sr
gaps, run, st = [], 0, 0
for i, v in enumerate(on):
    if not v:
        if run == 0: st = i
        run += 1
    else:
        if run:
            g = run*hop/sr
            if g >= 0.30: gaps.append(g)
        run = 0
if run:
    g = run*hop/sr
    if g >= 0.30: gaps.append(g)
gl = np.array(gaps)
W = 2549
print("马修母带 sr%d  总 %.1fs = %.1f 分  voiced %.1f (%.1f%%)  wpm %.0f  span %.0f" %
      (sr, tot, tot/60, voiced, 100*voiced/tot, W/voiced*60, W/tot*60))
print("  停顿 n=%d 合计 %.1fs  p50 %.2f  p90 %.2f  max %.2f" %
      (len(gl), gl.sum(), np.median(gl), np.percentile(gl, 90), gl.max()))
