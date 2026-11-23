# -*- coding: utf-8 -*-
"""慢包络电平归一：修掉 dots 输出"越念越小"的单调衰减，保留音节内动态。

做法：
  1) 20ms 帧 RMS(dB)；
  2) 只在有声帧上算 500ms 中值趋势（去掉音节级抖动）；
  3) 目标 = 有声趋势的中位数，增益 = 目标-趋势，限幅 ±6dB；
  4) 增益曲线再做 300ms 平滑，避免抽气感；
  5) 乘回去，最后整体归一到一个 RMS 上限（不削波）。

用法：
  python ch123_level.py 输入.wav 输出.wav [--max 6] [--target-rms -24]
"""
import sys

import numpy as np
import soundfile as sf


def _env_db(a, sr, hop=0.02):
    n = int(hop * sr)
    k = max(1, len(a) // n)
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    return 20 * np.log10(e + 1e-9), n


def _medfilt(x, w):
    if w < 3:
        return x
    w = int(w) | 1
    pad = w // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    out = np.empty_like(x)
    for i in range(len(x)):
        out[i] = np.median(xp[i:i + w])
    return out


def _smooth(x, w):
    if w < 2:
        return x
    ker = np.ones(int(w)) / float(int(w))
    pad = int(w) // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    return np.convolve(xp, ker, mode="valid")[:len(x)]


def level(a, sr, max_db=6.0, target_rms_db=-24.0, hop=0.02):
    """返回处理后波形。a: float32 mono."""
    db, n = _env_db(a, sr, hop)
    if len(db) < 8:
        return a
    loud = np.percentile(db, 90)
    voiced = db > (loud - 32.0)
    if voiced.sum() < 5:
        return a

    # 趋势：先在全部帧上中值滤波，再只用有声帧的插值
    trend = _medfilt(db, int(0.50 / hop))
    idx = np.arange(len(db))
    if voiced.sum() >= 3:
        trend = np.interp(idx, idx[voiced], trend[voiced])
    target = float(np.median(trend[voiced]))

    gain = np.clip(target - trend, -max_db, max_db)
    gain = _smooth(gain, int(0.30 / hop))
    # 静音段不做衰减（避免把底噪抬起来）
    gain = np.where(voiced, gain, 0.0)
    gain = _smooth(gain, int(0.10 / hop))

    frame_gain = np.repeat(gain, n)[:len(a)]
    if len(frame_gain) < len(a):
        frame_gain = np.pad(frame_gain, (0, len(a) - len(frame_gain)), mode="edge")

    y = a * (10 ** (frame_gain / 20.0))
    pk = float(np.max(np.abs(y)))
    if pk > 0.95:
        y *= 0.95 / pk
    rms = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9)
    if rms < target_rms_db - 0.5:
        y *= 10 ** ((target_rms_db - rms) / 20.0)
        pk = float(np.max(np.abs(y)))
        if pk > 0.95:
            y *= 0.95 / pk
    return y.astype(np.float32)


def decay_db(a, sr, hop=0.02):
    """首尾有声段电平差(dB)，正数=越念越小。"""
    db, n = _env_db(a, sr, hop)
    loud = np.percentile(db, 90)
    v = np.where(db > loud - 32.0)[0]
    if len(v) < 6:
        return 0.0
    q = max(2, len(v) // 5)
    return float(np.mean(db[v[:q]]) - np.mean(db[v[-q:]]))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    max_db = 6.0
    trms = -24.0
    args = sys.argv[3:]
    for i, x in enumerate(args):
        if x == "--max":
            max_db = float(args[i + 1])
        if x == "--target-rms":
            trms = float(args[i + 1])
    a, sr = sf.read(src, dtype="float32", always_2d=True)
    a = a.mean(1)
    before = decay_db(a, sr)
    y = level(a, sr, max_db, trms)
    after = decay_db(y, sr)
    sf.write(dst, y, sr, subtype="PCM_16")
    print("%s  decay %.1f -> %.1f dB  %.2fs" % (dst.split("/")[-1], before, after, len(y) / sr))


if __name__ == "__main__":
    main()
