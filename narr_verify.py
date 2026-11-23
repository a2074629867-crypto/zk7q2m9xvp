# -*- coding: utf-8 -*-
"""对新链路产物 _narr_new/out/*.wav 跑与旧库同一套 narr_check 判据。"""
import argparse, json, os, sys
sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf
import narr_check as NC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=r"G:/_setup/_narr_new/out")
    ap.add_argument("--out", default=r"G:/_setup/_narr_check_new")
    ap.add_argument("--whole", action="store_true", help="整块当一个 unit（默认按静音切句）")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.dir) if f.lower().endswith(".wav"))
    if a.limit:
        files = files[:a.limit]
    units = []
    for f in files:
        p = os.path.join(a.dir, f)
        x, sr = sf.read(p, dtype="float64", always_2d=True)
        x = x.mean(1)
        if a.whole:
            units.append((f[:-4], 0.0, len(x) / sr, x, sr))
        else:
            for i, (t0, t1) in enumerate(NC.cut_units(x, sr)):
                seg = x[int(t0 * sr): int(t1 * sr)]
                if len(seg) > int(0.3 * sr):
                    units.append(("%s#%02d" % (f[:-4], i), t0, t1, seg, sr))
    print("units=%d files=%d" % (len(units), len(files)), flush=True)
    NC.run(units, "narr_new", a.out)


if __name__ == "__main__":
    main()
