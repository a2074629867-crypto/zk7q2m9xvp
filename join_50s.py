# -*- coding: utf-8 -*-
"""拼接 50s 之后的 edit 成品，并切同段真人原声做锚点对照"""
import numpy as np, soundfile as sf

M = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
SR = sf.info(M).samplerate
O = "G:/_setup/dots_edit2/"

def rd(p):
    a, sr = sf.read(p, dtype="float32")
    if a.ndim > 1:
        a = a.mean(1)
    return a, sr

def gap(s, e):
    g, _ = sf.read(M, start=int(round(s * SR)), frames=int(round((e - s) * SR)), dtype="float32")
    if g.ndim > 1:
        g = g.mean(1)
    n = int(round(len(g) * 48000 / SR))
    return np.interp(np.linspace(0, len(g) - 1, n),
                     np.arange(len(g), dtype=np.float64), g).astype(np.float32)

a1, _ = rd(O + "PE1.wav")
a2, _ = rd(O + "PE2.wav")
a3, _ = rd(O + "PE3.wav")
g1 = gap(65.59, 66.53)   # 0.94s
g2 = gap(80.52, 81.36)   # 0.84s

full = np.concatenate([a1, g1, a2, g2, a3])
p = O + "P50_full_%.1fs.wav" % (len(full) / 48000)
sf.write(p, full, 48000, subtype="PCM_16")
print("edit 成品 %.2fs = %.2f + %.2f + %.2f + %.2f + %.2f" % (
    len(full) / 48000, len(a1) / 48000, len(g1) / 48000,
    len(a2) / 48000, len(g2) / 48000, len(a3) / 48000))
print("  ->", p)

# 真人原声同段 50.91~93.79
src, _ = sf.read(M, start=int(round(50.91 * SR)),
                 frames=int(round((93.79 - 50.91) * SR)), dtype="float32")
if src.ndim > 1:
    src = src.mean(1)
n = int(round(len(src) * 48000 / SR))
src = np.interp(np.linspace(0, len(src) - 1, n),
                np.arange(len(src), dtype=np.float64), src).astype(np.float32)
p2 = O + "P50_real_%.1fs.wav" % (len(src) / 48000)
sf.write(p2, src, 48000, subtype="PCM_16")
print("真人原声 %.2fs -> %s" % (len(src) / 48000, p2))
