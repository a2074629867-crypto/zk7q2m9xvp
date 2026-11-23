# -*- coding: utf-8 -*-
"""把重建好的极短句回填到 _audio_ch123/out/，先备份。

    _fill_short.py --dir _sweep/short2 --bak _bak_short_1122 --dry
    _fill_short.py --dir _sweep/short2 --bak _bak_short_1122
"""
import argparse
import glob
import hashlib
import os
import shutil

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_audio_ch123", "out")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def voiced_rms(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    if not len(v):
        return -99.0, len(y) / sr
    return float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)), len(y) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--bak", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.bak, exist_ok=True)

    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    print("%-9s %7s %7s %7s %7s %s" % ("id", "旧dur", "新dur", "旧RMS", "新RMS", "结果"))
    n_ok = 0
    for p in files:
        rid = os.path.basename(p).split("__")[0]
        dst = os.path.join(OUT, rid + ".wav")
        if not os.path.exists(dst):
            print("%-9s  缺原文件" % rid)
            continue
        o_rms, o_dur = voiced_rms(dst)
        n_rms, n_dur = voiced_rms(p)
        bad = abs(n_rms + 24.0) > 0.3 or not (0.15 <= n_dur <= 2.0)
        tag = "跳过(电平/时长不合)" if bad else ("预演" if a.dry else "回填")
        print("%-9s %7.2f %7.2f %7.1f %7.1f %s" % (rid, o_dur, n_dur, o_rms, n_rms, tag))
        if bad or a.dry:
            continue
        bp = os.path.join(a.bak, rid + ".wav")
        if not os.path.exists(bp):
            shutil.copy2(dst, bp)
        if md5(p) == md5(dst):
            pass
        shutil.copy2(p, dst)
        n_ok += 1
    print("\n回填 %d / %d（备份 → %s）" % (n_ok, len(files), a.bak))


if __name__ == "__main__":
    main()
