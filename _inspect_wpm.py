# -*- coding: utf-8 -*-
import json, os, sys
sys.path.insert(0, r"G:\_setup")
from _speedlib import wpm_in

ID = "c2_0191"
wl = json.load(open(r"G:\_setup\_wl_regen1123.json", encoding="utf-8"))
k = [x for x in wl if x.endswith("/" + ID + ".wav")]
print("key:", k)
v = wl[k[0]]
print("type", type(v).__name__, "len", len(v))
words = v if isinstance(v, list) else v.get("words")
if isinstance(words[0], dict):
    txt = " ".join(w["w"] if "w" in w else w.get("word", "") for w in words)
else:
    txt = " ".join(map(str, words))
print("n_words:", len(words))
print("text:", txt)

for p in [r"G:\_setup\_audio_ch123\out\c2_0191.wav",
          r"G:\_setup\_regen_1123\c2_0191.wav",
          r"G:\_setup\_regen_1123_norm\c2_0191.wav",
          r"G:\_setup\_regen_final\c2_0191.wav"]:
    print("%-52s wpm_in=%.1f  wpm_含停顿=%.1f" % (
        os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p),
        wpm_in(p, len(words)),
        wpm_in(p, len(words)) * 0 + len(words) / (__import__("soundfile").info(p).duration) * 60))
