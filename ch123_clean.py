# -*- coding: utf-8 -*-
"""干净版：只做单一整体增益到 -24dBFS，不做句内包络、不做限幅、不拉伸。

之前的 v2 链路（慢包络 + lookahead limiter）会把音节瞬态压平，听感"炸/糊"。
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB

TARGET = -24.0
# 峰值 ≤ −1 dBFS（REQUIREMENTS 技术红线，20*log10(0.891) = −1.00）。
# 原来 0.985 = −0.13dBFS，比红线高 0.87dB；mt_final_pause 那里还放到 0.999。
# 账本原话：波峰因数 23dB 时峰值天然落 −1dBFS，不需要 limiter。
CEIL = 0.891


def clean(a, sr):
    y = a.astype(np.float32).copy()
    db = RB.rms_voiced_db(y, sr)
    if abs(db - TARGET) > 0.05:
        y = y * (10 ** ((TARGET - db) / 20.0))
    pk = float(np.abs(y).max())
    if pk > CEIL:                       # 只有真会削波才整体回退，绝不压瞬态
        y = y * (CEIL / pk)
    return y


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/ch123"
    dst = sys.argv[2] if len(sys.argv) > 2 else "G:/_setup/ch123_clean"
    os.makedirs(dst, exist_ok=True)
    rows = []
    for f in sorted(glob.glob(os.path.join(src, "*.wav"))):
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        y = clean(a, sr)
        sf.write(os.path.join(dst, os.path.basename(f)), y, sr, subtype="PCM_16")
        rows.append((os.path.basename(f)[:-4], RB.rms_voiced_db(y, sr),
                     float(np.abs(y).max()), len(y) / sr))
    v = [r[1] for r in rows]
    print("n=%d  voiced %.2f ~ %.2f dB  跨度 %.2f" %
          (len(rows), min(v), max(v), max(v) - min(v)))
    print("peak max %.3f  时长 %.2f~%.2fs" %
          (max(r[2] for r in rows), min(r[3] for r in rows), max(r[3] for r in rows)))
    bad = [r[0] for r in rows if r[2] > 0.99]
    print("削波风险:", bad or "无")


if __name__ == "__main__":
    main()
