# -*- coding: utf-8 -*-
"""语速普查：按"有声时长"算 wpm，把停顿排除在外。

用法：python ch123_rate.py [目录]
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
from ch123_plan import INNER, PLAN

WORDS = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
WORDS.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
WHO.update({"I%02d" % i: w for i, (_, w, _, _) in enumerate(INNER)})


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/ch123"
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.wav"))):
        k = os.path.basename(f)[:-4]
        if k not in WORDS:
            continue
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        segs = RB.split_at_silence(a, sr, min_gap=0.22)
        voiced = sum(s1 - s0 for s0, s1 in segs)
        n = WORDS[k]
        rows.append(dict(k=k, who=WHO.get(k, "?"), n=n, dur=len(a) / sr, voiced=voiced,
                         wpm_voiced=n / voiced * 60 if voiced else 0,
                         wpm_total=n / (len(a) / sr) * 60))
    for who in ("C", "E"):
        sub = [r for r in rows if r["who"] == who]
        v = [r["wpm_voiced"] for r in sub]
        if not v:
            continue
        print("\n== %s  %d 条  有声语速 %.0f / %.0f / %.0f (min/med/max)  跨度 %.0f ==" %
              (who, len(sub), min(v), float(np.median(v)), max(v), max(v) - min(v)))
        for r in sorted(sub, key=lambda x: -x["wpm_voiced"])[:6]:
            print("  %-5s %5.0f wpm  %4.2fs 有声 %4.2fs  %2d 词" %
                  (r["k"], r["wpm_voiced"], r["dur"], r["voiced"], r["n"]))
        print("  ...")
        for r in sorted(sub, key=lambda x: x["wpm_voiced"])[:4]:
            print("  %-5s %5.0f wpm  %4.2fs 有声 %4.2fs  %2d 词" %
                  (r["k"], r["wpm_voiced"], r["dur"], r["voiced"], r["n"]))


if __name__ == "__main__":
    main()
