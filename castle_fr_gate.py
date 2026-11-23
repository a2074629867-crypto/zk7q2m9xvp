# -*- coding: utf-8 -*-
"""二次清理：对动态范围过小（有配乐残留）的片加噪声门 + 强降噪。
判据：10ms 帧能量 P90-P10 < 25 dB
"""
import os
import subprocess

import numpy as np
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
CLEAN = "G:/_setup/castle_fr_clean"
GATE = ("agate=threshold=0.035:ratio=4:attack=3:release=180,"
        "afftdn=nf=-22:tn=1,"
        "loudnorm=I=-20:TP=-1.5:LRA=11")


def dyn(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    n = int(0.01 * sr)
    k = len(a) // n
    if k < 3:
        return 99.0
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    return float(np.percentile(db, 90) - np.percentile(db, 10))


def main():
    fixed = []
    for grp in sorted(os.listdir(CLEAN)):
        d = os.path.join(CLEAN, grp)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".wav") or f.endswith("_bed.wav"):
                continue
            p = os.path.join(d, f)
            v = dyn(p)
            if v >= 25:
                continue
            tmp = p + ".tmp.wav"
            r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error",
                                "-i", p, "-af", GATE, "-ar", "48000", "-ac", "1",
                                "-c:a", "pcm_s16le", tmp], capture_output=True, text=True)
            if r.returncode == 0:
                os.replace(tmp, p)
                print("GATE %-22s %-24s %.1f -> %.1f dB" % (grp, f, v, dyn(p)))
                fixed.append((grp, f))
            else:
                print("ERR  %s %s" % (f, r.stderr[:80]))
    print("\n处理 %d 片" % len(fixed))


if __name__ == "__main__":
    main()
