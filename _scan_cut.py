# -*- coding: utf-8 -*-
"""细扫拼接硬切：30ms 级低谷 + 相邻帧跳变。"""
import sys

import numpy as np
import soundfile as sf


def scan(p, t0=0, t1=None, hop=0.005, win=0.02, dip_ms=30, dip_rel=18):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    n, h = int(win * sr), int(hop * sr)
    cnt = 1 + (len(y) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(cnt)[:, None]
    e = np.sqrt((y[idx] ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(e)
    times = np.arange(cnt) * hop
    sel = (times >= t0) & (times <= (t1 if t1 else 1e9))
    # 局部低谷：比左右各 60ms 内最高点低 dip_rel 以上，且持续 >= dip_ms
    k = int(0.06 / hop)
    lo = np.array([db[max(0, i - k):i + k + 1].max() for i in range(len(db))])
    dip = (lo - db) > dip_rel
    out = []
    i = 0
    while i < cnt:
        if dip[i]:
            j = i
            while j < cnt and dip[j]:
                j += 1
            if (j - i) * hop * 1000 >= dip_ms and sel[i:j].any():
                out.append(dict(t0=round(times[i], 3), t1=round(times[j - 1], 3),
                                ms=round((j - i) * hop * 1000),
                                depth_db=round(float(lo[i:j].max() - db[i:j].min()), 1),
                                floor=round(float(db[i:j].min()), 1)))
            i = j
        else:
            i += 1
    # 相邻 10ms 跳变
    jump = np.abs(np.diff(db))
    big = [(round(times[i], 3), round(float(jump[i]), 1)) for i in np.flatnonzero(jump > 20)]
    return out, big


if __name__ == "__main__":
    p = sys.argv[1]
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else None
    dips, jumps = scan(p, t0, t1)
    print("=== 低谷（>=30ms, >18dB）")
    for d in dips:
        print("  %6.2f-%6.2f  %4dms  depth %.1fdB  floor %.1fdB" %
              (d["t0"], d["t1"], d["ms"], d["depth_db"], d["floor"]))
    print("=== 相邻帧跳变 >20dB (共 %d)" % len(jumps))
    for t, j in jumps[:25]:
        print("   at %.3fs  %.1f dB" % (t, j))
