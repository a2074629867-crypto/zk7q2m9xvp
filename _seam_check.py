# -*- coding: utf-8 -*-
"""_seam_check.py —— 拆句接缝实测：独立生成的两段，接缝落差 vs 整句自然逗号落差。

用法：G:/Python310/python.exe _seam_check.py
"""
import json
import math
import os
import wave

import numpy as np
import parselmouth

ROOT = "G:/_setup"
SEAM = os.path.join(ROOT, "_seam")
UID = "N0156"


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        a = np.frombuffer(w.readframes(nf), dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def trim(a, sr, thr_db=-45.0):
    hop = max(1, int(0.01 * sr))
    k = len(a) // hop
    r = np.sqrt(np.mean(a[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(r + 1e-12)
    idx = np.where(db > thr_db)[0]
    if len(idx) == 0:
        return a
    return a[idx[0] * hop: min(len(a), (idx[-1] + 1) * hop)]


def f0_med(seg, sr):
    snd = parselmouth.Sound(seg, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=400.0)
    f = np.asarray(p.selected_array["frequency"], dtype=np.float64)
    f = f[f > 0]
    return float(np.median(f)) if len(f) else 0.0


def edge_f0(path, which, win=0.55):
    a, sr = rd(path)
    a = trim(a, sr)
    n = int(win * sr)
    seg = a[-n:] if which == "tail" else a[:n]
    return f0_med(seg, sr), len(a) / sr


def main():
    ana = json.load(open(os.path.join(ROOT, "_stress_ch1.json"), encoding="utf-8"))
    ref = None
    for p, v in ana.items():
        if v["uid"] == UID and str(v["seed"]) == "42":
            ref = v
            break
    if not ref:
        print("找不到整句版数据", UID)
        return

    words = ref["words"]
    i_copse = next((i for i, w in enumerate(words) if w["w"].lower().startswith("copse")), None)
    i_swept = next((i for i, w in enumerate(words) if w["w"].lower().startswith("swept")), None)
    if i_copse is None or i_swept is None:
        print("整句里找不到 copse / swept：", [w["w"] for w in words])
        return

    f_copse = words[i_copse]["f0"]
    f_swept = words[i_swept]["f0"]
    nat = abs(12.0 * math.log2(f_swept / f_copse)) if f_copse and f_swept else float("nan")

    a_tail, a_dur = edge_f0(os.path.join(SEAM, "a.wav"), "tail")
    b_head, b_dur = edge_f0(os.path.join(SEAM, "b.wav"), "head")
    seam = abs(12.0 * math.log2(b_head / a_tail)) if a_tail and b_head else float("nan")

    print("=== %s 拆句接缝实测 ===" % UID)
    print("整句原文：He walked to the window and looked out onto the copse, swept by the first heavy rain of the summer.")
    print()
    print("整句版（同 seed 42）")
    print("  copse  %.1f Hz   (f0_st %+.2f)" % (f_copse, words[i_copse]["f0_st"]))
    print("  Swept  %.1f Hz   (f0_st %+.2f)" % (f_swept, words[i_swept]["f0_st"]))
    print("  逗号自然落差 %.2f 半音" % nat)
    print()
    print("拆句版（各自独立生成）")
    print("  a.wav 末 0.55s  %.1f Hz   (时长 %.2fs)" % (a_tail, a_dur))
    print("  b.wav 首 0.55s  %.1f Hz   (时长 %.2fs)" % (b_head, b_dur))
    print("  接缝落差       %.2f 半音" % seam)
    print()
    print("=== 判定 ===")
    print("  接缝 / 自然 = %.2f×" % (seam / nat if nat else 0))
    print("  （≈1 表示拆句的接缝落差与整句本来就有的逗号落差同量级 ⇒ 听不出额外痕迹）")


if __name__ == "__main__":
    main()
