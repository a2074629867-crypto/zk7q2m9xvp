# -*- coding: utf-8 -*-
"""DNSMOS P.835 (SIG/BAK/OVL) + P.808 批量打分。

注意：speechmos 官方实现对 <9.01s 的音频用「循环复制」补长（audio = append(audio, audio)），
这会给短句引入虚假重复。本脚本提供两种补长方式，用于对比：
  loop  —— 官方做法（循环复制）
  pad   —— 尾部补静音到 9.01s（更接近「这段音频本身有多好」）
另外提供 seg 模式：只取最长语音段循环补长，避免静音稀释。
"""
import argparse
import glob
import os
import sys

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/Python310/Lib/site-packages")
from speechmos import dnsmos as DM

SR = 16000
INPUT_LEN = 9.01


def load16(path):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    if sr != SR:
        a = librosa.resample(a, orig_sr=sr, target_sr=SR)
    return np.clip(a, -1.0, 1.0)


def fit(a, mode):
    need = int(INPUT_LEN * SR)
    if len(a) >= need:
        return a
    if mode == "pad":
        return np.concatenate([a, np.zeros(need - len(a), dtype=np.float32)])
    reps = int(np.ceil(need / max(len(a), 1)))
    return np.tile(a, reps)[:need]


def score(a, mode="pad"):
    x = fit(a, mode)
    r = DM.run(x, SR, model_type="dnsmos")
    return float(r["sig_mos"]), float(r["bak_mos"]), float(r["ovrl_mos"]), float(r["p808_mos"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--mode", default="both", choices=["loop", "pad", "both"])
    args = ap.parse_args()

    files = []
    for p in args.paths:
        files.extend(sorted(glob.glob(p)) if any(c in p for c in "*?") else [p])

    modes = ["loop", "pad"] if args.mode == "both" else [args.mode]
    print("%-30s %6s  %s" % ("file", "dur", "  ".join("%-28s" % m for m in modes)))
    print("%-30s %6s  %s" % ("", "", "  ".join("%-28s" % "SIG / BAK / OVRL / P808" for _ in modes)))
    for f in files:
        a = load16(f)
        cells = []
        for m in modes:
            s, b, o, p = score(a, m)
            cells.append("%5.2f %5.2f %5.2f %5.2f" % (s, b, o, p))
        print("%-30s %5.2f  %s" % (os.path.basename(f), len(a) / SR, "  ".join(cells)), flush=True)


if __name__ == "__main__":
    main()
