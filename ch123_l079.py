# -*- coding: utf-8 -*-
"""L079 重做：I don't believe you. You're a liar. The Battle of Britain was in the war.

问题：旧版 4.48s peak 0.98 RMS -8dB 砖墙压缩（听感炸），且跨度仅 11Hz 语调平。
做法：整句一次生成，多变体对比。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

OUT = "G:/_setup/_exp79"
os.makedirs(OUT, exist_ok=True)

TEXT = "I don't believe you. You're a liar. The Battle of Britain was in the war."
ref, rtext = REFS["E"]

VARIANTS = [
    ("A", None, 42),
    ("B", "disgusted", 42),
    ("C", None, 44),
    ("D", "disgusted", 44),
]

if __name__ == "__main__":
    only = sys.argv[1:] or [v[0] for v in VARIANTS]
    for tag, emo, seed in VARIANTS:
        if tag not in only:
            continue
        body = TEXT
        if emo:
            body = "<emo, type=%s, level=2>%s</emo>" % (emo, TEXT)
        out = os.path.join(OUT, "L079_%s.wav" % tag)
        ok = R.gen(body, ref, rtext, 420, out, ["use_xvector=on"], seed=seed)
        print(tag, emo or "-", "seed", seed, "OK" if ok else "FAIL",
              round(os.path.getsize(out) / 1e3, 1) if ok else 0, "KB", flush=True)
