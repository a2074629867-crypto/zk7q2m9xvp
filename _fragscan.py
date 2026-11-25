# -*- coding: utf-8 -*-
"""_fragscan.py —— 全库「碎点」扫描（洞—短音—洞），按冒头强度分 A/B/C。

判据沿用 PROSODY_PLAN_V2 §11.3：
  内部洞 ≥0.15s；两洞之间有声 <0.35s 记为一处碎点；夹层峰值
  ≥−25 dBFS 记 A（真语音被劈开），−33~−25 记 B（弱残音），<−33 记 C（底噪抖动）。

用法：
  G:/Python310/python.exe -u _fragscan.py --dir _pause_fix2 _regen_final [--json out.json]
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def scan_one(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    hop = int(sr * 0.02)
    n = len(y) // hop
    if n < 10:
        return []
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - 20, -60)
    sil = db < thr
    runs, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.02 >= 0.15 and i > 3 and j < n - 3:
                runs.append((i * 0.02, (j - i) * 0.02))
            i = j
        else:
            i += 1
    out = []
    for (a, d1), (b, d2) in zip(runs, runs[1:]):
        g = b - (a + d1)
        if g >= 0.35:
            continue
        i1, i2 = int((a + d1) / 0.02), int(b / 0.02)
        if i2 <= i1:
            continue
        out.append(dict(t=round(a, 2), d1=round(d1, 2), gap=round(g, 2), d2=round(d2, 2),
                        peak=round(float(db[i1:i2].max()), 1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", nargs="+", required=True)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    ids = set(json.load(open(os.path.join(HERE, "_narr_ids716.json"), encoding="utf-8")))
    alld = {}
    for d in a.dir:
        full = os.path.join(HERE, d)
        if not os.path.isdir(full):
            print(d, "不存在")
            continue
        tot = {"A": 0, "B": 0, "C": 0}
        sidA, sidB, sidC = set(), set(), set()
        files, rows = 0, []
        for p in sorted(glob.glob(full + "/*.wav")):
            sid = os.path.basename(p)[:-4]
            if sid not in ids:
                continue
            files += 1
            for f in scan_one(p):
                k = "A" if f["peak"] >= -25 else ("B" if f["peak"] >= -33 else "C")
                tot[k] += 1
                {"A": sidA, "B": sidB, "C": sidC}[k].add(sid)
                f.update(sid=sid, cls=k)
                rows.append(f)
        print("%-16s 句 %3d   A %3d 处 / %3d 句    B %3d / %3d    C %3d / %3d"
              % (d, files, tot["A"], len(sidA), tot["B"], len(sidB), tot["C"], len(sidC)))
        alld[d] = rows
    if a.json:
        json.dump(alld, open(os.path.join(HERE, a.json), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("→", a.json)


if __name__ == "__main__":
    main()
