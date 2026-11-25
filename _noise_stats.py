# -*- coding: utf-8 -*-
"""全库噪声指标分布 —— 给闸门阈值做标定（不是拍数字）。

指标定义：
- floor_db   : 10ms 帧能量的 p10（底噪电平）
- snr_db     : p95 − p10（对白可懂度）
- zero_ms    : abs(x)==0 且连续 >=10ms 的累计时长（数字零 = 人声不可能出现）
- floor_jump : 200ms 块内 p10 的 max−min（段间底噪是否忽高忽低）
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def stats(p):
    x, sr = sf.read(p, dtype="float64")
    if x.ndim > 1:
        x = x.mean(1)
    w = int(0.01 * sr)
    n = len(x) // w
    fr = np.sqrt((x[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(fr)
    floor = float(np.percentile(db, 10))
    p95 = float(np.percentile(db, 95))
    p97 = float(np.percentile(db, 97))

    z = np.flatnonzero(x == 0.0)
    zero_ms = 0.0
    if len(z):
        runs = np.split(z, np.flatnonzero(np.diff(z) != 1) + 1)
        zero_ms = sum(len(r) / sr * 1000 for r in runs if len(r) / sr >= 0.010)

    blk = int(0.2 * sr)
    nb = len(x) // blk
    jumps = []
    if nb >= 3:
        for i in range(nb):
            seg = x[i * blk:(i + 1) * blk]
            m = len(seg) // w
            if m < 5:
                continue
            f2 = np.sqrt((seg[:m * w].reshape(m, w) ** 2).mean(1)) + 1e-12
            jumps.append(float(np.percentile(20 * np.log10(f2), 10)))
        floor_jump = (max(jumps) - min(jumps)) if jumps else 0.0
    else:
        floor_jump = 0.0

    return dict(dur=round(len(x) / sr, 2), floor=round(floor, 1),
                snr=round(p95 - floor, 1), p97_floor=round(p97 - floor, 1),
                zero_ms=round(zero_ms, 1), floor_jump=round(floor_jump, 1),
                peak=round(float(np.abs(x).max()), 3),
                rms=round(float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)), 1))


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_audio_ch123/out"
    ids = ""
    if len(sys.argv) > 2:
        ids = sys.argv[2]
    files = sorted(glob.glob(os.path.join(d, "*.wav")))
    if ids:
        want = {x.strip() for x in ids.split(",") if x.strip()}
        files = [f for f in files if os.path.basename(f)[:-4] in want]
    rows = {}
    for p in files:
        rows[os.path.basename(p)[:-4]] = stats(p)

    fl = [v["floor"] for v in rows.values()]
    sn = [v["snr"] for v in rows.values()]
    zz = [v["zero_ms"] for v in rows.values()]
    fj = [v["floor_jump"] for v in rows.values()]
    print("n=%d" % len(rows))
    for name, arr, unit in (("底噪", fl, "dB"), ("SNR", sn, "dB"),
                            ("数字零", zz, "ms"), ("段间底噪跨度", fj, "dB")):
        print("%-8s min %8.1f  p10 %8.1f  p50 %8.1f  p90 %8.1f  max %8.1f %s"
              % (name, min(arr), np.percentile(arr, 10), np.percentile(arr, 50),
                 np.percentile(arr, 90), max(arr), unit))
    print()
    for th, nm in ((-60, "底噪>−60"), (-55, "底噪>−55"), (-50, "底噪>−50")):
        print("%-10s %3d 条 (%.0f%%)" % (nm, sum(1 for v in fl if v > th),
                                         100 * sum(1 for v in fl if v > th) / len(fl)))
    for th in (30, 25, 20):
        print("SNR<%d     %3d 条 (%.0f%%)" % (th, sum(1 for v in sn if v < th),
                                               100 * sum(1 for v in sn if v < th) / len(sn)))
    print("有数字零   %3d 条 (%.0f%%)" % (sum(1 for v in zz if v > 0),
                                        100 * sum(1 for v in zz if v > 0) / len(zz)))
    print("跨度>6dB   %3d 条 (%.0f%%)" % (sum(1 for v in fj if v > 6),
                                        100 * sum(1 for v in fj if v > 6) / len(fj)))
    print("跨度>10dB  %3d 条 (%.0f%%)" % (sum(1 for v in fj if v > 10),
                                        100 * sum(1 for v in fj if v > 10) / len(fj)))
    json.dump(rows, open("_noise_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> _noise_stats.json")


if __name__ == "__main__":
    main()
