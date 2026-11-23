# -*- coding: utf-8 -*-
"""把 _split 里的分句重新拼接：trim + 响度对齐 + 按标点插静音。

    G:/Python310/python.exe bk_stitch.py 4 7 [--gain]

分句响度统一到 -24 dBFS（有声段 RMS），避免一句大一句小。
"""
import os
import sys
import wave

import numpy as np

OUT = "G:/_setup/dots_edit2"
TMP = "G:/_setup/dots_edit2/_split"
TARGET_DB = -24.0
LIMIT = 0.92


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def wr(p, a, sr):
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767.0).astype("<i2").tobytes())


def frames(a, sr, hop=0.01):
    n = int(hop * sr)
    k = len(a) // n
    if k < 3:
        return np.array([np.sqrt(np.mean(a ** 2) + 1e-12)])
    return np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])


def trim(a, sr, thr_db=-45.0, pad=0.04):
    e = frames(a, sr)
    db = 20 * np.log10(e + 1e-9)
    on = np.where(db > thr_db)[0]
    if len(on) == 0:
        return a
    n = int(0.01 * sr)
    s = max(0, int(on[0] * n - pad * sr))
    t = min(len(a), int((on[-1] + 1) * n + pad * sr))
    return a[s:t]


def loud(a, sr):
    e = frames(a, sr)
    db = 20 * np.log10(e + 1e-9)
    v = e[db > max(-45.0, np.percentile(db, 50))]
    if len(v) == 0:
        v = e
    cur = 20 * np.log10(np.mean(v) + 1e-9)
    g = 10 ** ((TARGET_DB - cur) / 20.0)
    return a * g


GAPS = {
    "2": [0.42, 0.42, 0.28],
    "4": [0.38, 0.30, 0.30],
    "5": [0.34, 0.34, 0.34, 0.30],
    "7": [0.42, 0.38],
}


def main():
    tags = [t for t in sys.argv[1:] if not t.startswith("-")]
    for tag in tags:
        files = sorted([f for f in os.listdir(TMP)
                        if f.startswith("BK%s_p" % tag) and f.endswith(".wav")])
        if not files:
            print("no parts for", tag)
            continue
        gaps = GAPS.get(tag, [0.35] * (len(files) - 1))
        pieces = []
        print("=== BK_%s ===" % tag)
        for i, f in enumerate(files):
            a, sr = rd(os.path.join(TMP, f))
            a = trim(a, sr)
            b4 = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-9)
            a = loud(a, sr)
            af = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-9)
            print("  %-12s %5.2fs  RMS %6.1f -> %6.1f dBFS  peak %.2f" %
                  (f, len(a) / sr, b4, af, np.max(np.abs(a))))
            pieces.append(a)
            if i < len(files) - 1:
                pieces.append(np.zeros(int(gaps[i] * sr), dtype=np.float32))
        y = np.concatenate(pieces)
        pk = np.max(np.abs(y))
        if pk > LIMIT:
            y *= LIMIT / pk
            print("  peak %.2f -> limiter" % pk)
        wr(os.path.join(OUT, "BK_%s_r.wav" % tag), y, sr)
        print("  -> BK_%s_r.wav  %.2fs  peak %.2f" %
              (tag, len(y) / sr, np.max(np.abs(y))))


if __name__ == "__main__":
    main()
