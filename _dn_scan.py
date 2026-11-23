# -*- coding: utf-8 -*-
"""_dn_scan.py —— 全库成品「到底有多脏」扫描（只读，不改文件）

口径要点：数字零帧（全零 = -inf）不算噪声，必须剔除，否则 10 分位永远是 -240。
只统计「有信号但很低」的帧，那才是真底噪。
"""
import glob
import json
import os

import numpy as np
import soundfile as sf

OUT = "G:/_setup/_dn_scan.json"


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    if len(y) < w:
        return np.array([-120.0]), np.array([0.0])
    n = 1 + (len(y) - w) // h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    zero = np.abs(seg).max(1) == 0
    return 20 * np.log10(e), zero


def hf_ratio(y, sr, lo=6000, hi=12000):
    n, hop = 1024, 512
    if len(y) < n * 2:
        return 0.0
    win = np.hanning(n)
    f = np.fft.rfftfreq(n, 1 / sr)
    mh = (f >= lo) & (f < hi)
    ah = at = 0.0
    for i in range(0, 1 + (len(y) - n) // hop, 4):
        P = np.abs(np.fft.rfft(y[i * hop:i * hop + n] * win)) ** 2
        ah += P[mh].sum()
        at += P.sum()
    return float(ah / max(at, 1e-20))


def main():
    files = sorted(glob.glob("G:/_setup/_audio_ch123/out/*.wav"))
    rows = {}
    for i, f in enumerate(files):
        rid = os.path.splitext(os.path.basename(f))[0]
        y, sr = sf.read(f, dtype="float64", always_2d=True)
        y = y.mean(1)
        db, zero = frame_db(y, sr)
        nz = db[~zero]                       # 剔除数字零帧
        nz_quiet = nz[nz < np.percentile(nz, 50)] if len(nz) else np.array([-120.0])
        rows[rid] = {
            "dur": round(len(y) / sr, 3),
            "floor_nz": round(float(np.percentile(nz, 10)), 1) if len(nz) else -240.0,
            "floor_quiet": round(float(np.median(nz_quiet)), 1) if len(nz_quiet) else -240.0,
            "zero_pct": round(float(zero.mean() * 100), 1),
            "sp_rms": round(float(np.mean(db[db > -45])), 2) if (db > -45).any() else -120.0,
            "hf": round(hf_ratio(y, sr), 5),
        }
        if i % 40 == 0:
            print(f"{i}/{len(files)} {rid}", flush=True)
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    fl = np.array([v["floor_nz"] for v in rows.values()])
    z = np.array([v["zero_pct"] for v in rows.values()])
    print(f"\nn={len(rows)}")
    print("floor_nz   p10 %.1f  p25 %.1f  p50 %.1f  p75 %.1f  p90 %.1f" % tuple(
        np.percentile(fl, [10, 25, 50, 75, 90])))
    print("zero_pct   p50 %.1f%%  (数字零占时长比)" % np.median(z))
    for t in (-45, -40, -35):
        print(f"floor_nz > {t}: {(fl > t).sum()} 条")
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()
