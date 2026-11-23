# -*- coding: utf-8 -*-
"""全库电平统一 v2：先限峰再归一，避免"峰值卡住导致 RMS 提不上去"。

v1 的问题：L068/L076/L083/L087 这些波峰因数很高的条目，一乘增益就撞 0.891 上限，
被限幅拉回去，结果还是 -31dB，跨度只收到 7.8dB。

v2 流程：
  1) 句内慢包络归一（修"越念越小"），限幅 12dB；
  2) 整条增益到 TARGET（不限峰）；
  3) lookahead 限幅器压到 -1dBFS（只压尖峰，不动 RMS）；
  4) 迭代补增益，直到 voiced RMS 进 ±0.4dB。

用法：python ch123_unify.py [--target -24] [--src ch123] [--dst ch123_u]
"""
import glob
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_level as L
import ch123_rebuild as RB

TARGET = -24.0
CEIL = 0.891  # -1 dBFS


def _maxfilt(x, w):
    """滑动最大值（前视/后视都取，保证峰值不被漏掉）。"""
    if w <= 1:
        return x
    pad = w // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    out = np.empty_like(x)
    for i in range(len(x)):
        out[i] = xp[i:i + w].max()
    return out


def limiter(y, sr, ceil=CEIL, look=0.006, rel=0.12):
    """峰值限幅：只压超过 ceil 的部分，释放平滑。"""
    n = max(3, int(look * sr))
    env = _maxfilt(np.abs(y), n)
    g = np.minimum(1.0, ceil / np.maximum(env, 1e-9))
    # 释放平滑（增益只能慢慢回升）
    a = np.exp(-1.0 / (rel * sr))
    out = np.empty_like(g)
    cur = 1.0
    for i in range(len(g)):
        cur = g[i] if g[i] < cur else (a * cur + (1 - a) * g[i])
        out[i] = cur
    return (y * out).astype(np.float32)


def proc(a, sr, max_db=12.0):
    y = L.level(a, sr, max_db=max_db, target_rms_db=TARGET)
    for _ in range(3):
        db = RB.rms_voiced_db(y, sr)
        if abs(db - TARGET) < 0.4:
            break
        y = y * (10 ** ((TARGET - db) / 20.0))
        y = limiter(y, sr)
    if float(np.abs(y).max()) > CEIL:
        y = limiter(y, sr)
    return y.astype(np.float32)


def main():
    args = sys.argv[1:]
    target = TARGET
    src, dst = "G:/_setup/ch123", "G:/_setup/ch123"
    max_db = 12.0
    for i, x in enumerate(args):
        if x == "--target":
            target = float(args[i + 1])
        if x == "--src":
            src = args[i + 1]
        if x == "--dst":
            dst = args[i + 1]
        if x == "--maxdb":
            max_db = float(args[i + 1])
    os.makedirs(dst, exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dst):
        bak = "G:/_setup/ch123_pre_unify"
        if not os.path.exists(bak):
            shutil.copytree(src, bak)
            print("备份 →", bak)
    rows = []
    for f in sorted(glob.glob(os.path.join(src, "*.wav"))):
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        before = RB.rms_voiced_db(a, sr)
        d0 = L.decay_db(a, sr)
        y = proc(a, sr, max_db)
        after = RB.rms_voiced_db(y, sr)
        d1 = L.decay_db(y, sr)
        sf.write(os.path.join(dst, os.path.basename(f)), y, sr, subtype="PCM_16")
        rows.append((os.path.basename(f), before, after, d0, d1, float(np.abs(y).max())))
    for r in rows:
        flag = "" if abs(r[2] - TARGET) < 0.6 else "  ← 偏"
        print("%-9s %6.1f → %6.1f dB   decay %5.1f → %4.1f   peak %.2f%s" %
              (r[0], r[1], r[2], r[3], r[4], r[5], flag), flush=True)
    if rows:
        a0 = [r[1] for r in rows]
        a1 = [r[2] for r in rows]
        bad = [r[0] for r in rows if abs(r[2] - TARGET) >= 0.6]
        print("\n跨度 %.1f dB → %.1f dB   衰减最大 %.1f → %.1f dB" %
              (max(a0) - min(a0), max(a1) - min(a1),
               max(r[3] for r in rows), max(r[4] for r in rows)))
        print("未达标 %d 条 %s" % (len(bad), ",".join(bad)))


if __name__ == "__main__":
    main()
