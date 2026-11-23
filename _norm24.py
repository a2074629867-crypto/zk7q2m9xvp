# -*- coding: utf-8 -*-
"""把交付目录里的某条强制归一到 -24.00 dBFS（voiced RMS），幂等。

用法：G:/Python310/python.exe _norm24.py c2_0312 [c2_0313 ...]
"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

DIRS = ["G:/_setup/_audio_ch123/out", "G:/_setup/_audio_ch123/out_paused"]


def main():
    ids = sys.argv[1:]
    if not ids:
        print("用法: _norm24.py <id> [id...]")
        return 1
    for i in ids:
        for d in DIRS:
            p = os.path.join(d, i + ".wav")
            if not os.path.exists(p):
                print("缺", p)
                continue
            y, sr = sf.read(p, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            y = np.ascontiguousarray(y, dtype="float32")
            for _ in range(6):
                lv, _, _ = voiced_db(y, sr)
                if lv is None or abs(lv + 24.0) < 0.04:
                    break
                y = (y * 10 ** ((-24.0 - lv) / 20.0)).astype("float32")
                if float(np.abs(y).max()) > 0.97:
                    y = (y * (0.97 / float(np.abs(y).max()))).astype("float32")
            sf.write(p, y, sr, subtype="PCM_16")
            lv, _, _ = voiced_db(np.ascontiguousarray(y), sr)
            print("%-9s %-11s %.2f dBFS  %.2fs" % (i, os.path.basename(d), lv or -99, len(y) / sr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
