# -*- coding: utf-8 -*-
"""F0 半音域夸张化后处理（parselmouth / Praat 实现）

诊断：生成音频的 F0 起伏只有原声的 57%（4.31~4.81 vs 原声 6.07 半音），
听感即"每个词的语气差别不够"。这里在 **对数(半音)域** 放大 F0 偏离量：

    f0' = med * (f0 / med) ** k        k>1 放大起伏，中位数音高保持不变

用 Praat 的 Manipulation 只替换 pitch tier 再 overlap-add 重合成，
谱包络 / 时长不动 ⇒ 音色与语速不变，只改韵律曲线。

注：pyworld 0.3.5 在本机 numpy 1.23 下 cheaptrick/d4c/stonemask 全报
    TypeError（ABI 不兼容），故改用 parselmouth。

用法：
  python -u exaggerate_praat.py --in X.wav --out Y.wav --ks 1.2,1.4,1.6,2.0
  python -u exaggerate_praat.py --in-dir A --out-dir B --ks 1.4
"""
import argparse
import os
import sys

import numpy as np
import parselmouth
from parselmouth.praat import call


def exaggerate(in_wav, out_wav, k=1.4, floor=60.0, ceil=400.0, period=0.01):
    snd = parselmouth.Sound(in_wav)
    manip = call(snd, "To Manipulation", period, floor, ceil)
    pt = call(manip, "Extract pitch tier")
    n = int(call(pt, "Get number of points"))
    if n < 5:
        raise RuntimeError("pitch tier 点数过少: %d" % n)
    vals = np.array([call(pt, "Get value at index", i + 1) for i in range(n)], dtype=float)
    med = float(np.median(vals))
    call(pt, "Formula", "if self > 0 then %.8f * (self / %.8f) ^ %.4f else 0 fi" % (med, med, k))
    call([pt, manip], "Replace pitch tier")
    out = call(manip, "Get resynthesis (overlap-add)")
    out.save(out_wav, "WAV")
    return n, med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out", dest="outp")
    ap.add_argument("--in-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--ks", default="1.2,1.4,1.6,2.0")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    ks = [float(v) for v in a.ks.split(",") if v]

    if a.inp:
        for k in ks:
            out = a.outp if len(ks) == 1 else a.outp.replace(".wav", "_k%02d.wav" % int(round(k * 10)))
            n, med = exaggerate(a.inp, out, k)
            print("[ok] k=%.2f pts=%d med=%.1fHz -> %s" % (k, n, med, os.path.basename(out)), flush=True)
        return

    os.makedirs(a.out_dir, exist_ok=True)
    for f in sorted(x for x in os.listdir(a.in_dir) if x.endswith(".wav")):
        for k in ks:
            out = os.path.join(a.out_dir, "%s%s_k%02d.wav" % (f[:-4], a.suffix, int(round(k * 10))))
            try:
                n, med = exaggerate(os.path.join(a.in_dir, f), out, k)
                print("[ok] %-14s k=%.2f pts=%4d med=%.1f -> %s" % (f, k, n, med, os.path.basename(out)), flush=True)
            except Exception as e:
                print("[!!] %s k=%.2f 失败: %s" % (f, k, e), flush=True)


if __name__ == "__main__":
    main()
