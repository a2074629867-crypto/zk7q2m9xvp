# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, r"G:/_setup")
sys.path.insert(0, r"G:/_setup/emo_bench")
os.chdir(r"G:/_setup")
import mt_seg_drift as D
import soundfile as sf

for f in ["c1_0020", "c1_0043", "c2_0321", "c1_0002"]:
    p = "_audio_ch123/out/%s.wav" % f
    if not os.path.exists(p):
        print(f, "MISSING"); continue
    y, sr = sf.read(p)
    r = D.one(p)
    ws = D.windows(y, sr) if hasattr(D, "windows") else None
    usable = None
    if ws:
        usable = sum(1 for w in ws if w["voiced"] >= 0.60 and w["f0"])
    print(f, "sr=%d" % sr, "dur=%.2f" % r["dur"], "n_win=%s" % r["n_win"],
          "usable=%s" % usable, r["verdict"])
