"""按多个起点切同一段，归一电平后落盘，供 ASR 挑选正确边界。"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

OUT = "G:/_setup/_sweep/cutsweep"


def cut(src, dst, a, b, pre=0.03, post=0.06):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    s = max(0, int((a - pre) * sr))
    e = min(len(y), int((b + post) * sr))
    z = np.ascontiguousarray(y[s:e].astype("float32"))
    k = int(0.012 * sr)
    if len(z) > 2 * k:
        z[:k] *= np.linspace(0, 1, k, dtype="float32")
        z[-k:] *= np.linspace(1, 0, k, dtype="float32")
    lv, _, _ = voiced_db(z, sr)
    g = 10 ** ((-24.0 - lv) / 20.0) if lv else 1.0
    if float(np.abs(z).max()) * g > 0.97:
        g = 0.97 / float(np.abs(z).max())
    z = (z * g).astype("float32")
    sf.write(dst, z, sr, subtype="PCM_16")
    lv2, _, _ = voiced_db(z, sr)
    return len(z) / sr, lv, lv2


JOBS = [
    # (tag, src, [(start, end), ...])
    ("c3_0652", "G:/_setup/_sweep/cand22/c3_0652b__s7.wav", [(0.24, 0.60), (0.28, 0.60), (0.31, 0.60)]),
    ("c3_0654", "G:/_setup/_sweep/cand23/c3_0654__s47.wav", [(0.24, 0.60), (0.28, 0.60), (0.31, 0.60)]),
    ("c1_0187", "G:/_setup/_sweep/cand23/c1_0187__s7.wav", [(1.06, 2.62), (1.10, 2.62), (1.14, 2.62)]),
]

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, src, spans in JOBS:
        for i, (a, b) in enumerate(spans):
            p = os.path.join(OUT, "%s_v%d.wav" % (tag, i))
            d, lv, lv2 = cut(src, p, a, b)
            print("%-8s v%d  %.2f-%.2f -> dur %.2f  rms %.2f->%.2f" % (tag, i, a, b, d, lv, lv2))
    print("OK", OUT)
