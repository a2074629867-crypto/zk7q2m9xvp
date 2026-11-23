# -*- coding: utf-8 -*-
"""平静句重建：切掉载体词 → rubberband 保音高降速 → 按断句插入停顿 → 归一。

为什么不用后期整体 time-stretch 完事：橡皮筋会把停顿一起拉长，而这句话的问题是
「吐字太快 + 断点不够」，所以先降速再把停顿补到指定长度，两件事分开控。

用法：
  G:/Python310/python.exe _rebuild_calm.py --src .../cw23__d00_s23.wav \
      --cut 0.45 --tempo 0.72 \
      --pause 1.15:0.42 --pause 2.71:0.28 \
      --out G:/_setup/_sweep/final/c2_0312.wav
  （--pause 的时间是**降速后**的时间轴；不确定就先 --dry 跑一遍看词界）
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--cut", type=float, default=0.0)
    ap.add_argument("--tempo", type=float, default=1.0)
    ap.add_argument("--pause", action="append", default=[],
                    help="降速后时间轴上的插入点:长度，如 1.15:0.42")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    y, sr = sf.read(a.src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    if a.cut > 0:
        y = y[int(a.cut * sr):]
        print("切掉前 %.2fs" % a.cut)

    tmp = a.out + ".cut.wav"
    sf.write(tmp, y, sr, subtype="PCM_16")
    stretched = a.out + ".rb.wav"
    if abs(a.tempo - 1.0) > 1e-6:
        stretch(tmp, stretched, a.tempo)
    else:
        stretched = tmp

    z, sr2 = sf.read(stretched, dtype="float32")
    if z.ndim > 1:
        z = z.mean(1)
    z = np.ascontiguousarray(z)

    ins = sorted((float(x.split(":")[0]), float(x.split(":")[1])) for x in a.pause)
    parts, prev = [], 0
    for t, d in ins:
        c = int(t * sr2)
        parts.append(z[prev:c])
        parts.append(np.zeros(int(d * sr2), dtype="float32"))
        prev = c
    parts.append(z[prev:])
    out = np.concatenate(parts) if parts else z

    out = fades(out, sr2, 10)
    out = norm24(out, sr2)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sf.write(a.out, out, sr2, subtype="PCM_16")
    print("输出 %s  dur=%.2fs  lv=%.2f" % (a.out, len(out) / sr2, voiced_db(out, sr2)))
    for f in (tmp, stretched):
        if f != tmp or abs(a.tempo - 1.0) > 1e-6:
            if os.path.exists(f) and f not in (a.out,):
                os.remove(f)


if __name__ == "__main__":
    main()
