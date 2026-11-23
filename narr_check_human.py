# -*- coding: utf-8 -*-
"""用同一套 narr_check 判据量真人旁白（donor），作为 F0/突跳率的真实基线。"""
import sys, os, json, argparse
sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import narr_check as NC

ap = argparse.ArgumentParser()
ap.add_argument("--wav", default=r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav")
ap.add_argument("--sec", type=float, default=120.0)
ap.add_argument("--out", default=r"G:/_setup/_narr_check_human")
a = ap.parse_args()

x, sr = sf.read(a.wav, dtype="float64", always_2d=True)
x = x.mean(1)
x = x[: int(a.sec * sr)]
units = []
for i, (t0, t1) in enumerate(NC.cut_units(x, sr)):
    seg = x[int(t0 * sr): int(t1 * sr)]
    if len(seg) > int(0.3 * sr):
        units.append(("H%02d" % i, t0, t1, seg, sr))
print("human units=%d  sec=%.0f" % (len(units), a.sec), flush=True)
NC.run(units, "human_donor", a.out)
