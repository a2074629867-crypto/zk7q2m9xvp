# -*- coding: utf-8 -*-
"""碎点检测（洞-短音-洞），并给出 A/B/C 分档。

用法：
  G:/Python310/python.exe -u _fragcheck.py <wav> [<wav> ...]
  G:/Python310/python.exe -u _fragcheck.py --dir D1 D2 --ids c1_0174,...
"""
import argparse
import json
import os

import numpy as np
import soundfile as sf


def frags(path, minlen=0.15, gapmax=0.35):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    hop = int(sr * 0.02)
    n = len(y) // hop
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - 20, -60)
    sil = db < thr
    runs = []
    i = 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.02 >= minlen and i > 3 and j < n - 3:
                runs.append((i * 0.02, (j - i) * 0.02))
            i = j
        else:
            i += 1
    out = []
    for (a, d1), (b, d2) in zip(runs, runs[1:]):
        g = b - (a + d1)
        if g < gapmax:
            i1, i2 = int((a + d1) / 0.02), int(b / 0.02)
            gseg = db[i1:i2] if i2 > i1 else np.array([-99.0])
            fl1 = db[int(a / 0.02):i1]
            fl2 = db[i2:int(min(n, (b + d2) / 0.02))]
            fl = float(np.median(np.concatenate([fl1, fl2]))) if len(fl1) and len(fl2) else -60.0
            out.append(dict(t=round(a, 2), d1=round(d1, 2), gap=round(g, 2), d2=round(d2, 2),
                            peak=round(float(gseg.max()), 1), floor=round(fl, 1),
                            prom=round(float(gseg.max()) - fl, 1)))
    return round(len(y) / sr, 2), out, len(runs)


def grade(f):
    if f["peak"] >= -25:
        return "A"
    if f["peak"] >= -33:
        return "B"
    return "C"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="*")
    ap.add_argument("--dir", nargs="*", default=[])
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    pairs = [(w, None) for w in a.wavs]
    if a.dir and a.ids:
        ids = [x.strip() for x in a.ids.split(",") if x.strip()]
        for d in a.dir:
            for sid in ids:
                p = os.path.join(d, sid + ".wav")
                if os.path.exists(p):
                    pairs.append((p, sid))
    for p, sid in pairs:
        if not os.path.exists(p):
            print("%-46s 缺失" % p)
            continue
        dur, fr, nh = frags(p)
        cnt = {"A": 0, "B": 0, "C": 0}
        for f in fr:
            cnt[grade(f)] += 1
        print("%-46s %6.2fs 洞%3d 碎点%2d  A%2d B%2d C%2d" % (
            p.replace("\\", "/").split("/")[-2] + "/" + os.path.basename(p), dur, nh, len(fr),
            cnt["A"], cnt["B"], cnt["C"]))
        for f in fr:
            if grade(f) == "A":
                print("      A @%6.2f 洞%.2f+%.2f(峰%.0f)+%.2f" % (
                    f["t"], f["d1"], f["gap"], f["peak"], f["d2"]))


if __name__ == "__main__":
    main()
