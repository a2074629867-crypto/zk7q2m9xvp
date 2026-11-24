#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""裁掉 no-ref-text 产物多出来的首尾静音，并对齐到 voiced RMS −24 dBFS。

背景（2026-11-24）：66 条 `--no-ref-text` 产物覆盖率达标、lead 归零，但**尾部静音
中位 0.31s**（旧版 0.01s）。直接算 wpm 会把尾巴算成"念得慢"（中位 −15%），
去掉首尾静音后实际语速中位只差 −1%。

用法：
  python _trim_notxt66.py --src _sweep/notxt66 --out _sweep/notxt66_trim
"""
import argparse
import glob
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HEAD_KEEP = 0.03      # 保留 30ms 起音，太少会切掉爆破音
TAIL_KEEP = 0.10      # 保留 100ms 尾音，太少会听出"被掐断"
THR = -50.0           # 绝对阈值（dBFS），与 _post_fix / _dn_scan 一致


def voiced_span(y, sr):
    hop, win = int(0.01 * sr), int(0.025 * sr)
    n = 1 + (len(y) - win) // hop
    if n < 1:
        return 0.0, len(y) / sr
    idx = np.clip(np.arange(win)[None, :] + hop * np.arange(n)[:, None], 0, len(y) - 1)
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    v = np.where(db > THR)[0]
    if not len(v):
        return 0.0, len(y) / sr
    return v[0] * hop / sr, (v[-1] * hop + win) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="_sweep/notxt66")
    ap.add_argument("--out", default="_sweep/notxt66_trim")
    a = ap.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    src = a.src if os.path.isabs(a.src) else os.path.join(root, a.src)
    out = a.out if os.path.isabs(a.out) else os.path.join(root, a.out)
    os.makedirs(out, exist_ok=True)

    import _deliver as DL

    files = sorted(glob.glob(os.path.join(src, "*.wav")))
    print("%-26s %6s %6s %6s %6s" % ("file", "新旧", "首切", "尾切", "rms"))
    n = 0
    for f in files:
        y, sr = sf.read(f, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        d0 = len(y) / sr
        s, e = voiced_span(y, sr)
        h = max(0.0, s - HEAD_KEEP)
        t = min(d0, e + TAIL_KEEP)
        seg = y[int(h * sr):int(t * sr)].copy()
        if len(seg) < int(0.05 * sr):
            seg = y.copy()                     # 太短就不切，别造出空文件
            h, t = 0.0, d0
        # 10ms 淡入淡出，避免切点爆音
        k = int(0.01 * sr)
        if len(seg) > 4 * k:
            seg[:k] *= np.linspace(0, 1, k)
            seg[-k:] *= np.linspace(1, 0, k)
        op = os.path.join(out, os.path.basename(f))
        sf.write(op, seg.astype(np.float32), sr, subtype="PCM_16")
        lv, pk = DL.norm24(op)                  # 回填标准：voiced RMS −24 dBFS
        print("%-26s %6.2f→%5.2f %6.2f %6.2f %6.2f" % (
            os.path.basename(f), d0, len(seg) / sr, h, d0 - t, lv))
        n += 1
    print("\n处理 %d 条 → %s" % (n, out))


if __name__ == "__main__":
    main()
