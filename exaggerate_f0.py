# -*- coding: utf-8 -*-
"""F0 半音域夸张化后处理 —— 直接针对"韵律被抹平"。

诊断：生成音频的半音域 F0 起伏只有原声的 ~56%（3.49 vs 6.26 半音），
听感就是"每个词的语气差别不够"。这里在 **对数(半音)域** 线性放大 F0 偏离量：

    st  = 12 * log2(f0 / f0_median)
    st' = k * st                       ← k>1 放大起伏，保持音高中位数不变
    f0' = f0_median * 2^(st'/12)

用 WORLD(pyworld) 只重合成 F0，谱包络 / 非周期性沿用原音频，
所以音色基本不变、只改韵律曲线。

用法：
  python -u exaggerate_f0.py --in X.wav --out Y.wav --k 1.5
  python -u exaggerate_f0.py --in-dir A --out-dir B --ks 1.3,1.5,1.8,2.2
"""
import argparse
import os
import sys

import numpy as np
import pyworld as pw
import soundfile as sf


def exaggerate(x, sr, k=1.5, floor=60.0, ceil=400.0, frame_period=5.0):
    x = np.ascontiguousarray(x, dtype=np.float64)
    f0, t = pw.harvest(x, sr, f0_floor=floor, f0_ceil=ceil, frame_period=frame_period)
    f0 = pw.stonemask(x, sr, t, f0)
    sp = pw.cheaptrick(x, sr, t, f0)
    ap = pw.d4c(x, sr, t, f0)

    v = f0 > 0
    n = int(v.sum())
    if n > 20:
        med = float(np.median(f0[v]))
        st = 12.0 * np.log2(f0[v] / med)
        f0[v] = med * np.power(2.0, (k * st) / 12.0)
    y = pw.synthesize(f0, sp, ap, sr)
    return y.astype(np.float32), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out", dest="outp")
    ap.add_argument("--in-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--ks", default="1.3,1.5,1.8,2.2")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()

    ks = [float(v) for v in a.ks.split(",") if v]

    if a.inp:
        x, sr = sf.read(a.inp)
        for k in ks:
            y, n = exaggerate(x, sr, k)
            out = a.outp if len(ks) == 1 else a.outp.replace(".wav", "_k%02d.wav" % int(k * 10))
            sf.write(out, y, sr)
            print("[ok] k=%.2f voiced=%d -> %s" % (k, n, out), flush=True)
        return

    files = sorted(f for f in os.listdir(a.in_dir) if f.endswith(".wav"))
    os.makedirs(a.out_dir, exist_ok=True)
    for f in files:
        x, sr = sf.read(os.path.join(a.in_dir, f))
        for k in ks:
            y, n = exaggerate(x, sr, k)
            out = os.path.join(a.out_dir, "%s%s_k%02d.wav" % (f[:-4], a.suffix, int(k * 10)))
            sf.write(out, y, sr)
            print("[ok] %-12s k=%.2f voiced=%4d -> %s" % (f, k, n, os.path.basename(out)), flush=True)


if __name__ == "__main__":
    main()
