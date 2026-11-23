# -*- coding: utf-8 -*-
"""切同一批单元在 v2 / v4b 里的对应片段，用于 A/B。"""
import sys, json, os
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

def load(wav):
    x, sr = sf.read(wav, dtype="float32", always_2d=True)
    return x.mean(1), sr

def offsets(js, sr):
    rows = json.load(open(js, encoding="utf-8"))["rows"]
    pos, off = 0, {}
    for i, r in enumerate(rows):
        off[r["uid"]] = (pos, pos + int(round(r["dur"] * sr)))
        pos += int(round(r["dur"] * sr))
        if i < len(rows) - 1:
            pos += int(round(r["gap"] * sr))
    return off

JOBS = [
    ("v2_raw", "_chap_ch1_raw2.wav", "_chap_ch1_raw2.json", "N0050", "N0055", "_ab/pair_v2.wav"),
    ("v4b",    "_chap_ch1_v4b.wav", "_chap_ch1_v4b.json", "N0050", "N0055", "_ab/pair_v4b.wav"),
]
for tag, wav, js, u0, u1, out in JOBS:
    x, sr = load(wav)
    off = offsets(js, sr)
    # 头尾各留 0.1s，避免切在语音上
    a = max(0, off[u0][0] - int(0.1 * sr))
    b = min(len(x), off[u1][1] + int(0.3 * sr))
    seg = x[a:b]
    sf.write(out, seg, sr, subtype="PCM_16")
    print("%-8s %6.2fs  → %s" % (tag, len(seg) / sr, out))

# 前 2 分钟切片
for src, out in [("_chap_ch1_v4b.wav", "_ab/ch1_v4b_2min.wav"),
                 ("_chap_ch1_v4b.wav", "_ab/ch1_v4b_first60.wav")]:
    x, sr = load(src)
    n = sr * (120 if "2min" in out else 60)
    sf.write(out, x[:n], sr, subtype="PCM_16")
    print("%s %.0fs" % (out, n / sr))
