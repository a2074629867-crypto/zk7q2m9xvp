"""第二轮边界扫描：按多个起点切，ASR 选边界。"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

OUT = "G:/_setup/_sweep/cs2"


def cut(src, dst, a, b, pre=0.02, post=0.05):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    s = max(0, int((a - pre) * sr))
    e = min(len(y), int((b + post) * sr))
    z = np.ascontiguousarray(y[s:e].astype("float32"))
    k = int(0.010 * sr)
    if len(z) > 2 * k:
        z[:k] *= np.linspace(0, 1, k, dtype="float32")
        z[-k:] *= np.linspace(1, 0, k, dtype="float32")
    lv, _, _ = voiced_db(z, sr)
    g = 10 ** ((-24.0 - lv) / 20.0) if lv else 1.0
    if float(np.abs(z).max()) * g > 0.97:
        g = 0.97 / float(np.abs(z).max())
    z = (z * g).astype("float32")
    sf.write(dst, z, sr, subtype="PCM_16")
    return len(z) / sr


JOBS = [
    ("c3_0652", "G:/_setup/_sweep/cand22/c3_0652b__s7.wav", [0.14, 0.17, 0.20, 0.23], 0.60),
    ("c3_0652b", "G:/_setup/_sweep/cand22/c3_0652b__s11.wav", [0.14, 0.20], 0.62),
    ("c3_0654", "G:/_setup/_sweep/cand23/c3_0654__s47.wav", [0.18, 0.21, 0.24], 0.60),
    ("c3_0837", "G:/_setup/_sweep/cand23/c3_0837__s23.wav", [0.42, 0.48, 0.54], 1.20),
    ("c2_0275", "G:/_setup/_sweep/cand23/c2_0275__s11.wav", [0.40, 0.46, 0.52], 1.05),
    ("c1_0187", "G:/_setup/_sweep/cand23/c1_0187__s7.wav", [1.15, 1.25, 1.35, 1.45], 2.62),
]

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, src, starts, end in JOBS:
        for s in starts:
            p = os.path.join(OUT, "%s_%03d.wav" % (tag, int(s * 100)))
            d = cut(src, p, s, end)
            print("%-10s @%.2f dur %.2f" % (tag, s, d))
