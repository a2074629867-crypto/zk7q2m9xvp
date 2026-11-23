# -*- coding: utf-8 -*-
"""极短句裁切：模型对 1~2 词会生成 1.1~1.3s（前后各挂 0.2~0.5s 静音），
这里按能量裁到有声区间，再归一到 voiced RMS −24 dBFS。

    _cut_short.py --dir _selftest/short_notxt --out _sweep/short_final
"""
import argparse
import glob
import os

import numpy as np
import soundfile as sf

SR_OK = 48000


def trim(y, sr, lead=0.03, tail=0.10, thr_db=-50):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    v = np.where(db > thr_db)[0]
    if not len(v):
        return y
    a = max(0, int(v[0] * hop - lead * sr))
    b = min(len(y), int(v[-1] * hop + fl + tail * sr))
    return y[a:b]


def norm24(y, sr):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    lv = float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) if len(v) else -99
    if lv < -80:
        return y, lv
    y = (y * 10 ** ((-24.0 - lv) / 20)).astype(np.float32)
    pk = float(np.abs(y).max())
    if pk > 0.95:
        y = (y * (0.95 / pk)).astype(np.float32)
    return y, lv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fade", type=float, default=0.008)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    print("%-34s %6s %6s %6s" % ("file", "dur", "voiced", "RMS"))
    for p in sorted(glob.glob(os.path.join(a.dir, "*.wav"))):
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        y = trim(y, sr)
        y, lv = norm24(y.astype(np.float32), sr)
        k = int(a.fade * sr)
        if len(y) > 2 * k:
            y[:k] *= np.linspace(0, 1, k, dtype=np.float32)
            y[-k:] *= np.linspace(1, 0, k, dtype=np.float32)
        out = os.path.join(a.out, os.path.basename(p))
        sf.write(out, y, sr, subtype="PCM_16")
        # 复测有声长度
        fl, hop = int(0.025 * sr), int(0.01 * sr)
        n = 1 + (len(y) - fl) // hop
        idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
        db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
        vo = (db > db.max() - 40).sum() * hop / sr
        print("%-34s %6.2f %6.2f %6s" % (os.path.basename(p), len(y) / sr, vo,
                                         "%.1f" % lv if lv > -80 else "-"))


if __name__ == "__main__":
    main()
