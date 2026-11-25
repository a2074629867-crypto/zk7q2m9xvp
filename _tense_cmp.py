# -*- coding: utf-8 -*-
"""对比紧张句：现役（旧 nervous 参考，F0 335 喊）vs 重生成（soft 参考 F0 189）。"""
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf


def prof(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f[f > 0]
    n = int(0.025 * sr)
    h = int(0.01 * sr)
    c = 1 + max(0, (len(y) - n) // h)
    idx = np.clip(np.arange(n)[None, :] + h * np.arange(c)[:, None], 0, len(y) - 1)
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    return dict(dur=round(len(y) / sr, 2), f0=int(np.median(v)) if len(v) else 0,
                p90=int(np.percentile(v, 90)) if len(v) else 0,
                floor=round(float(np.percentile(db, 1)), 1),
                peak=round(float(np.abs(y).max()), 2))


rows = {}
for p in sorted(glob.glob("G:/_setup/_regen_tense/*.wav")):
    name = os.path.basename(p)
    rid = name.split("__")[0].replace("ts_", "")
    rows[rid] = p

print("%-9s %-28s %-28s" % ("id", "现役(out)", "重生成(soft)"))
f0s_old, f0s_new = [], []
for rid in sorted(rows):
    a = "G:/_setup/_audio_ch123/out/%s.wav" % rid
    if not os.path.exists(a):
        continue
    pa, pb = prof(a), prof(rows[rid])
    f0s_old.append(pa["f0"])
    f0s_new.append(pb["f0"])
    flag = "  ← F0 降 %d" % (pa["f0"] - pb["f0"]) if pa["f0"] - pb["f0"] > 60 else ""
    print("%-9s F0%4d p90%4d fl%6.1f %5.2fs   F0%4d p90%4d fl%6.1f %5.2fs%s"
          % (rid, pa["f0"], pa["p90"], pa["floor"], pa["dur"],
             pb["f0"], pb["p90"], pb["floor"], pb["dur"], flag))

if f0s_old:
    print("\n现役 F0 中位 %.0f / p90 %.0f  |  重生成 F0 中位 %.0f / p90 %.0f"
          % (np.median(f0s_old), np.percentile(f0s_old, 90),
             np.median(f0s_new), np.percentile(f0s_new, 90)))
    print("现役 >300Hz（喊）: %d 条  |  重生成 >300Hz: %d 条"
          % (sum(1 for x in f0s_old if x > 300), sum(1 for x in f0s_new if x > 300)))
