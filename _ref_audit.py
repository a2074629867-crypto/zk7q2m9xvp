# -*- coding: utf-8 -*-
"""参考库体检：底噪 / SNR / F0。参数不统一是成品不连续的根源。

实测（2026-11-24）：_ref9_clean 33 条底噪跨 −42.6 ~ −77.3 dB（34.7 dB 落差），
而成品底噪基本等于参考底噪 + 2~4 dB —— 所以「统一参考」比事后除噪更根本。
"""
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _dn_uniform as DU


def prof(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f[f > 0]
    floor, p97, p5 = DU.floor_db_of(y, sr)
    return dict(dur=round(len(y) / sr, 2), sr=sr, floor=round(floor, 1),
                p97=round(p97, 1), snr=round(DU.snr_of(y, sr), 1),
                f0=int(np.median(v)) if len(v) else 0,
                voiced=round(float((f > 0).mean()), 2),
                peak=round(float(np.abs(y).max()), 3),
                bits=sf.info(p).subtype)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_ref9_clean"
    rows = {}
    print("%-26s %6s %7s %6s %6s %5s %6s" % ("file", "dur", "floor", "snr", "f0", "pk", "bits"))
    for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
        k = os.path.basename(p)[:-4]
        q = prof(p)
        rows[k] = q
        print("%-26s %6.2f %7.1f %6.1f %6d %5.2f %6s" %
              (k, q["dur"], q["floor"], q["snr"], q["f0"], q["peak"], q["bits"]))
    if rows:
        fl = [v["floor"] for v in rows.values()]
        sn = [v["snr"] for v in rows.values()]
        print("\n底噪  min %.1f  p50 %.1f  max %.1f  **跨度 %.1f dB**" %
              (min(fl), np.median(fl), max(fl), max(fl) - min(fl)))
        print("SNR   min %.1f  p50 %.1f  max %.1f  **跨度 %.1f dB**" %
              (min(sn), np.median(sn), max(sn), max(sn) - min(sn)))
        print("SNR < 30 的条数：%d / %d" % (sum(1 for x in sn if x < 30), len(sn)))
        print("底噪 > -60 的条数：%d / %d" % (sum(1 for x in fl if x > -60), len(fl)))
    json.dump(rows, open("_ref_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> _ref_audit.json")


if __name__ == "__main__":
    main()
