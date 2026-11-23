# -*- coding: utf-8 -*-
"""造已知坏样本：拿交付版好音，注入 5 种「明显不行」的退化。

用途：给自然度指标做 known-answer 标定（AUC）。
退化类型都是我们真实遇到过的：
  hole     词中挖 80ms 静音（吞字/断裂）
  chop     0.25s 切碎重排（机器音）
  clip     ×4 增益硬削波（破音）
  lowpass  3.5k 低通（闷/糊）
  stutter  60ms 片段重复 3 次（结巴感）
"""
import json
import os
import sys

import numpy as np
import soundfile as sf
import librosa

OUT = "G:/_setup/_nat_deg"
PICK = "G:/_setup/_mt_pick"
UIDS = ["N0194", "N0239", "N0254", "N0552", "N0755"]


def hole(x, sr):
    a = int(0.35 * len(x))
    b = a + int(0.08 * sr)
    y = x.copy()
    y[a:b] = 0
    return y


def chop(x, sr):
    seg = int(0.25 * sr)
    parts = [x[i:i + seg] for i in range(0, len(x), seg)]
    rng = np.random.default_rng(7)
    rng.shuffle(parts)
    return np.concatenate(parts)


def clip(x, sr):
    return np.clip(x * 4.0, -1.0, 1.0)


def lowpass(x, sr):
    return _lp(x, sr)


def _lp(x, sr, fc=3500.0):
    from scipy.signal import butter, sosfilt
    sos = butter(8, fc / (sr / 2), btype="low", output="sos")
    return sosfilt(sos, x).astype(np.float32)


def stutter(x, sr):
    a = int(0.30 * len(x))
    rep = x[a:a + int(0.06 * sr)]
    return np.concatenate([x[:a], rep, rep, rep, x[a:]])


def mono(x, sr):
    """整句压成单音高（去语调）—— 典型的韵律不自然"""
    import pyworld as pw
    f0, t = pw.harvest(np.ascontiguousarray(x.astype(np.float64)), sr)
    sp = pw.cheaptrick(x.astype(np.float64), f0, t, sr)
    ap = pw.d4c(x.astype(np.float64), f0, t, sr)
    v = f0 > 0
    if v.sum() < 10:
        return x
    f0c = np.where(v, float(np.median(f0[v])), 0.0)
    y = pw.synthesize(f0c, sp, ap, sr)
    n = min(len(y), len(x))
    return y[:n].astype(np.float32)


def flatamp(x, sr):
    """把逐帧能量压到中位（每音节等响，重音全丢）"""
    step = max(1, int(0.02 * sr))
    n = len(x) // step
    fr = x[: n * step].reshape(n, step)
    r = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    med = float(np.median(r[r > 1e-3])) if (r > 1e-3).any() else float(np.median(r))
    g = med / np.maximum(r, 1e-9)
    g = np.clip(g, 0.25, 4.0)
    y = (fr * g[:, None]).reshape(-1)
    return np.concatenate([y, x[n * step:]]).astype(np.float32)


def jitter(x, sr):
    """每 100ms 随机变速 ±25%（节奏机械）"""
    rng = np.random.default_rng(11)
    step = int(0.10 * sr)
    out = []
    for i in range(0, len(x), step):
        seg = x[i:i + step]
        if len(seg) < 50:
            out.append(seg); continue
        f = float(rng.uniform(0.75, 1.25))
        m = max(32, int(len(seg) / f))
        y = np.interp(np.linspace(0, len(seg) - 1, m), np.arange(len(seg)), seg)
        out.append(y.astype(np.float32))
    return np.concatenate(out)


DEGS = dict(hole=hole, chop=chop, clip=clip, lowpass=lowpass, stutter=stutter,
            mono=mono, flatamp=flatamp, jitter=jitter)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for u in UIDS:
        src = os.path.join(PICK, u + ".wav")
        x, sr = sf.read(src, dtype="float32", always_2d=False)
        if x.ndim > 1:
            x = x.mean(1)
        rows.append(dict(uid=u, deg="orig", wav=src, label="GOOD", ref=src))
        for name, fn in DEGS.items():
            y = fn(x.copy(), sr)
            p = os.path.join(OUT, "%s_%s.wav" % (u, name))
            sf.write(p, y, sr)
            rows.append(dict(uid=u, deg=name, wav=p, label="BAD", ref=src))
    json.dump(rows, open(os.path.join(OUT, "manifest.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    print("built", len(rows), "files ->", OUT)


if __name__ == "__main__":
    main()
