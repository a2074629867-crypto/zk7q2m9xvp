# -*- coding: utf-8 -*-
"""全库过一遍 RNNoise（arnndn），压掉 demucs 残留的配乐/底噪。
cwd 固定 G:/_setup，模型用相对路径 std.rnnn（ffmpeg 对 Windows 绝对路径解析有坑）。
"""
import os
import subprocess

import numpy as np
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
CLEAN = "G:/_setup/castle_fr_clean"
WORK = "G:/_setup"
AF = "arnndn=m=std.rnnn,highpass=f=80:poles=2,loudnorm=I=-20:TP=-1.5:LRA=11"


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
    n_ok = 0
    for grp in sorted(os.listdir(CLEAN)):
        d = os.path.join(CLEAN, grp)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".wav") or f.endswith("_bed.wav"):
                continue
            p = os.path.join(d, f)
            before = dyn(p)
            tmp = os.path.join(WORK, "_rn_tmp.wav")
            r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error",
                                "-i", p, "-af", AF, "-ar", "48000", "-ac", "1",
                                "-c:a", "pcm_s16le", tmp], capture_output=True, text=True, cwd=WORK)
            if r.returncode:
                print("ERR %-24s %s" % (f, r.stderr.strip()[:80]))
                continue
            os.replace(tmp, p)
            n_ok += 1
            print("OK   %-22s %-24s 动态 %5.1f -> %5.1f dB" % (grp, f, before, dyn(p)))
    print("\nRNNoise 处理 %d 片" % n_ok)


if __name__ == "__main__":
    main()
