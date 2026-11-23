# -*- coding: utf-8 -*-
"""拼 A/B 试听包：旧（nervous_2 参考）vs 新（用户自带 c185 参考）。

用法：G:/Python310/python.exe _ab_pack.py <out.wav> <label>=<path> ...
"""
import sys

import numpy as np
import soundfile as sf

SR = 48000


def rd(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    assert sr == SR, (p, sr)
    return y.astype("float32")


def main():
    out = sys.argv[1]
    seq = []
    for a in sys.argv[2:]:
        lab, _, p = a.partition("=")
        seq.append((lab, p))
    gap = np.zeros(int(0.85 * SR), dtype="float32")
    chunks, tab, t = [], [], 0.0
    for lab, p in seq:
        y = rd(p)
        tab.append((lab, t, t + len(y) / SR))
        chunks += [y, gap]
        t += len(y) / SR + 0.85
    y = np.concatenate(chunks)
    sf.write(out, y, SR, subtype="PCM_16")
    print("总 %.2fs -> %s" % (len(y) / SR, out))
    for lab, a, b in tab:
        print("  %-22s %5.2f ~ %5.2f" % (lab, a, b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
