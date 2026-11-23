# -*- coding: utf-8 -*-
"""平静句重建 v2：降速 → 用「本句自己的底噪」延长停顿（不插零）→ 归一。

与 v1 的差别：
1. 停顿不再插 np.zeros —— 纯数字静音听起来「空洞、没有呼吸感」。
   改为取该间隙自身的低电平噪声（room tone）循环延长，保留空气感。
2. 插入点自动检测（能量谷），不再硬编码时间。
3. tempo 可一次跑多档，便于 A/B。

用法：
  G:/Python310/python.exe _rebuild_calm2.py --src xx.wav --cut 0.46 \
      --tempo 0.80 --gaps 2 --extra 0.22,0.16 --out out.wav
"""
import argparse
import os
import subprocess

import numpy as np
import soundfile as sf

FF = r"E:/tool/oopz/ffmpeg.exe"
SR = 48000


def stretch(src, dst, tempo):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality:transients=crisp" % tempo,
                    "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def fades(y, sr, ms=10):
    k = int(ms / 1000 * sr)
    if len(y) > 2 * k:
        y[:k] *= np.linspace(0, 1, k, dtype="float32")
        y[-k:] *= np.linspace(1, 0, k, dtype="float32")
    return y


def voiced_db(y, sr):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    return float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) if len(v) else None


def norm24(y, sr):
    lv = voiced_db(y, sr)
    if lv is None:
        return y
    y = (y * 10 ** ((-24.0 - lv) / 20.0)).astype("float32")
    pk = float(np.abs(y).max())
    if pk > 0.97:
        y = (y * (0.97 / pk)).astype("float32")
    return y


def find_gaps(y, sr, thr_db=-42.0, min_len=0.08):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    vo = db > thr_db
    gaps, start = [], None
    for k, v in enumerate(vo):
        if (not v) and start is None:
            start = k
        if v and start is not None:
            a, b = start * hop, k * hop
            if (b - a) / sr >= min_len:
                gaps.append((a, b))
            start = None
    if start is not None:
        b = len(y)
        if (b - start * hop) / sr >= min_len:
            gaps.append((start * hop, b))
    return gaps


def room_tone(y, a, b, sr, need):
    """从间隙自身取底噪，循环到 need 长度；带交叉淡化，避免周期感。"""
    seg = y[a:b]
    if len(seg) < int(0.05 * sr):
        seg = y[max(0, a - int(0.05 * sr)):b]
    if len(seg) < int(0.03 * sr) or float(np.abs(seg).max()) < 1e-5:
        # 间隙本身几乎是数字零，补一层很轻的舒适噪声（-62dB 低通）
        rng = np.random.default_rng(7)
        seg = (rng.standard_normal(int(0.3 * sr)) * 10 ** (-62 / 20)).astype("float32")
        seg = np.convolve(seg, np.ones(9, dtype="float32") / 9, mode="same").astype("float32")
    reps = int(np.ceil(need / len(seg)))
    out = np.tile(seg, reps)[:need].astype("float32")
    k = int(0.012 * sr)
    if len(out) > 2 * k:
        out[:k] *= np.linspace(0, 1, k, dtype="float32")
        out[-k:] *= np.linspace(1, 0, k, dtype="float32")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--cut", type=float, default=0.0)
    ap.add_argument("--tempo", type=float, default=1.0)
    ap.add_argument("--gaps", type=int, default=2, help="取最长的几处间隙来加长")
    ap.add_argument("--extra", default="", help="逐个额外长度，逗号分隔，如 0.22,0.16")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    y, sr = sf.read(a.src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    if a.cut > 0:
        y = y[int(a.cut * sr):]

    tmp = a.out + ".cut.wav"
    sf.write(tmp, y, sr, subtype="PCM_16")
    if abs(a.tempo - 1.0) > 1e-6:
        rb = a.out + ".rb.wav"
        stretch(tmp, rb, a.tempo)
        z, sr2 = sf.read(rb, dtype="float32")
        if z.ndim > 1:
            z = z.mean(1)
        z = np.ascontiguousarray(z)
    else:
        rb = None
        z, sr2 = y, sr

    gaps = find_gaps(z, sr2)
    gaps = sorted(gaps, key=lambda g: -(g[1] - g[0]))[: a.gaps]
    gaps = sorted(gaps)
    extras = [float(x) for x in a.extra.split(",") if x.strip()] if a.extra else []
    if not extras:
        extras = [0.20] * len(gaps)

    parts, prev = [], 0
    for k, (ga, gb) in enumerate(gaps):
        ex = int(extras[min(k, len(extras) - 1)] * sr2)
        mid = (ga + gb) // 2
        parts.append(z[prev:mid])
        parts.append(room_tone(z, ga, gb, sr2, ex))
        prev = mid
    parts.append(z[prev:])
    out = np.concatenate(parts) if parts else z

    out = fades(out, sr2, 10)
    out = norm24(out, sr2)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sf.write(a.out, out, sr2, subtype="PCM_16")
    print("输出 %s dur=%.2fs lv=%.2f gaps=%s" % (
        a.out, len(out) / sr2, voiced_db(out, sr2),
        [(round(x[0] / sr2, 2), round((x[1] - x[0]) / sr2, 2)) for x in gaps]))
    for f in (tmp, rb):
        if f and os.path.exists(f):
            os.remove(f)


if __name__ == "__main__":
    main()
