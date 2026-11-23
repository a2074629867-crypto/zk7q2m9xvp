# -*- coding: utf-8 -*-
"""只对旁白（speaker==narrator）跑 narr_check 的 L1 韵律体检。

narr_check.py 的 --dir 会把对白也扫进来（955 条），旁白链路的验收口径只该是 716 条。
不改 narr_check 本身，直接 import 它的 run()。
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import narr_check as NC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cast", default="G:/_setup/_castle_en_ch123_cast.jsonl")
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--out", default="G:/_setup/_narr_check")
    ap.add_argument("--who", default="narrator")
    a = ap.parse_args()

    ids = []
    for line in open(a.cast, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("speaker") == a.who:
            ids.append(r["id"])
    ids = sorted(set(ids))
    print("%s: %d 条" % (a.who, len(ids)), flush=True)

    units = []
    miss = 0
    for i in ids:
        p = os.path.join(a.dir, i + ".wav")
        if not os.path.exists(p):
            miss += 1
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        units.append((i, 0.0, len(y) / sr, y, sr))
    print("载入 %d 条（缺 %d）" % (len(units), miss), flush=True)

    NC.run(units, "旁白 %d 条" % len(units), a.out, role="narr")


if __name__ == "__main__":
    main()
