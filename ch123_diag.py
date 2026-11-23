# -*- coding: utf-8 -*-
"""诊断「越说越小声 / 内部气声 / 节奏断裂」。

    G:/Python310/python.exe ch123_diag.py [topN]

指标：
  atten  = 尾段有声 RMS − 首段有声 RMS（dB，负=越来越小声）
  gap    = 最长内部静音（s）
  hush   = 内部 < −55dB 且持续 >0.4s 的段落数（气声/空转）
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

WIN = 0.02


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def analyze(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(1)
    n = int(WIN * sr)
    k = len(a) // n
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    voiced = np.where(db > -45)[0]
    if len(voiced) < 5:
        return None
    # 去掉首尾静音
    lo, hi = voiced[0], voiced[-1]
    body = db[lo:hi + 1]
    # 首尾各取 30% 的有声帧
    v = np.where(body > -45)[0]
    if len(v) < 8:
        return None
    q = max(3, len(v) // 3)
    head = body[v[:q]].mean()
    tail = body[v[-q:]].mean()
    # 内部最长静音
    mx = cur = 0
    for x in body:
        cur = 0 if x > -45 else cur + 1
        mx = max(mx, cur)
    # 气声段（连续 < -55 且长于 0.4s）
    hush = 0
    cur = 0
    for x in body:
        if x < -55:
            cur += 1
            if cur * WIN >= 0.4:
                hush += 1 if cur * WIN < 0.42 else 0
        else:
            cur = 0
    return dict(dur=len(a) / sr, atten=tail - head, gap=mx * WIN, hush=hush,
                head=head, tail=tail)


def main():
    topn = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = []
    for p in sorted(glob.glob("G:/_setup/ch123/*.wav")):
        r = analyze(p)
        if r:
            rows.append((os.path.basename(p)[:-4], r))
    rows.sort(key=lambda x: x[1]["atten"])
    print("%-6s %6s %7s %6s %5s %7s %7s" % ("key", "dur", "atten", "gap", "hush", "head", "tail"))
    for k, r in rows[:topn]:
        print("%-6s %6.2f %7.1f %6.2f %5d %7.1f %7.1f" %
              (k, r["dur"], r["atten"], r["gap"], r["hush"], r["head"], r["tail"]))
    print("--- 衰减中位 %.1f dB / 内部静音中位 %.2fs ---" %
          (np.median([r["atten"] for _, r in rows]),
           np.median([r["gap"] for _, r in rows])))


if __name__ == "__main__":
    main()
