# -*- coding: utf-8 -*-
"""much 那一段逐帧 F0 —— 确认那 8.8 st 上跳是真音高，不是八度跟踪错。"""
import json, os
import numpy as np, soundfile as sf, parselmouth

ID = "c2_0191"
old = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_words.json", encoding="utf-8")).items()}
new = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_regen1123.json", encoding="utf-8")).items()}

for tag, rec, path in (("验收版", old[ID], r"G:\_setup\_audio_ch123\out\%s.wav" % ID),
                       ("三档版", new[ID], r"G:\_setup\_regen_final\%s.wav" % ID)):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    s = parselmouth.Sound(y.astype(np.float64), sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    W = rec["words"]
    i = [k for k, w in enumerate(W) if w["w"].strip().lower() == "much"][0]
    t0 = float(W[i - 1]["start"])
    t1 = float(W[min(i + 1, len(W) - 1)]["end"])
    print("\n=== %s  [been → much → impressed]  %.2f~%.2fs ===" % (tag, t0, t1))
    t = t0
    while t < t1:
        f = p.get_value_at_time(t)
        if f is None or np.isnan(f):
            print("  %.2f    --" % t)
        else:
            st = 12 * np.log2(f / 100.0)
            bar = "#" * max(0, int((st + 20) * 1.2))
            print("  %.2f  %6.1fHz %+6.2fst %s" % (t, f, st, bar))
        t += 0.02
