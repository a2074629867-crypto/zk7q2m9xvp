# -*- coding: utf-8 -*-
import glob
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
from _rate import rate  # noqa: E402
import numpy as np
import parselmouth
import soundfile as sf

rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}


def info(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f[f > 0]
    return dict(dur=round(len(y) / sr, 2), f0=int(np.median(v)) if len(v) else 0,
                peak=round(float(np.abs(y).max()), 2))


print("%-9s %-38s %-38s" % ("id", "现役", "重生成(_refs_v3)"))
for p in sorted(glob.glob("G:/_setup/_regen_hopper/*.wav")):
    rid = os.path.basename(p).split("__")[0].replace("hl_", "")
    a = "G:/_setup/_audio_ch123/out/%s.wav" % rid
    t = rows[rid]["text"]
    ra, rb = rate(a, t), rate(p, t)
    ia, ib = info(a), info(p)
    print("%-9s wpm %4.0f %4.2fs F0 %3d pk %.2f   wpm %4.0f %4.2fs F0 %3d pk %.2f"
          % (rid, ra["wpm"], ia["dur"], ia["f0"], ia["peak"],
             rb["wpm"], ib["dur"], ib["f0"], ib["peak"]))
