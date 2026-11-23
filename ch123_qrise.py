# -*- coding: utf-8 -*-
"""句尾升调：把最后 span 秒切成 3 段连续窗口，逐段 rubberband 升调（formant 保持）。

    G:/Python310/python.exe ch123_qrise.py in.wav out.wav [top=3.0] [span=0.30]

与前一版的差别：连续分段（不重叠铺满），最后一段覆盖真正的句尾，
保证收尾处一定是最高的音，不会出现「抬起来又掉下去」。
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
NSEG = 3


def rd(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def voiced_end(a, sr, thr_db=-45.0, win=0.01):
    n = int(win * sr)
    k = max(1, len(a) // n)
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    idx = np.where(db > thr_db)[0]
    return (idx[-1] + 1) * win if len(idx) else len(a) / sr


def shift(a, sr, semi):
    if abs(semi) < 0.01:
        return a
    fin = os.path.join(tempfile.gettempdir(), "_qs_in.wav")
    fout = os.path.join(tempfile.gettempdir(), "_qs_out.wav")
    sf.write(fin, a.astype(np.float32), sr)
    r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", fin,
                        "-af", "rubberband=pitch=%.5f:formant=preserved" % (2 ** (semi / 12.0)),
                        "-ar", str(sr), "-ac", "1", fout], capture_output=True, text=True)
    if r.returncode != 0:
        return a
    b, _ = rd(fout)
    if len(b) < len(a):
        b = np.pad(b, (0, len(a) - len(b)))
    return b[:len(a)]


def rise(a, sr, top=3.0, span=0.30, xf=0.012):
    n = len(a)
    end = min(len(a), int((voiced_end(a, sr) + 0.02) * sr))
    t0 = max(0, end - int(span * sr))
    seg = a[t0:end].copy()
    if len(seg) < int(0.12 * sr):
        return a
    L = len(seg) // NSEG
    out = []
    for k in range(NSEG):
        s = k * L
        e = len(seg) if k == NSEG - 1 else (k + 1) * L
        semi = top * (k + 1) / NSEG
        out.append(shift(seg[s:e], sr, semi))
    # 交叉淡化拼接
    nx = max(1, int(xf * sr))
    y = out[0]
    for nxt in out[1:]:
        if len(y) < nx or len(nxt) < nx:
            y = np.concatenate([y, nxt])
            continue
        f = np.linspace(0, 1, nx, dtype=np.float32)
        y = np.concatenate([y[:-nx], y[-nx:] * (1 - f) + nxt[:nx] * f, nxt[nx:]])
    if len(y) < len(seg):
        y = np.pad(y, (0, len(seg) - len(y)))
    res = a.copy()
    res[t0:t0 + len(seg)] = y[:len(seg)]
    return res


def main():
    src, dst = sys.argv[1], sys.argv[2]
    top = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    span = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
    a, sr = rd(src)
    y = np.clip(rise(a, sr, top, span), -1, 1)
    sf.write(dst, y.astype(np.float32), sr)
    print("%s -> %s  top=%+.1f st span=%.2fs" % (src, dst, top, span))


if __name__ == "__main__":
    main()
