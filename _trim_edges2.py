# -*- coding: utf-8 -*-
"""交付前收尾：掐掉首尾多余静音（只动边界，不动内容）。

问题：模型对「一个词的台词」会给出 3 秒多的文件，其中 88% 是静音
（实测 c3_0863「No.」dur 3.36s，有声只 0.41s）。这种死时长拼进成品里，
播放器上就是「说完话还在那儿干等」，也被用户听成「拖」。

规则：首尾各留 0.05 / 0.12 秒，5ms 淡入淡出。中间一律不动。
"""
import argparse
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _shorten_pause import voiced_runs


def trim(y, sr, head=0.05, tail=0.12):
    r = voiced_runs(y, sr)
    if not r:
        return y, False
    a = max(0, r[0][0] - int(head * sr))
    b = min(len(y), r[-1][1] + int(tail * sr))
    if b - a >= len(y) - 8:
        return y, False
    out = y[a:b]
    f = max(1, int(0.005 * sr))
    out[:f] *= np.linspace(0, 1, f)
    out[-f:] *= np.linspace(1, 0, f)
    return out, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out_deliver")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    want = {x.strip() for x in a.ids.split(",") if x.strip()}
    n = 0
    saved = 0.0
    for f in sorted(glob.glob(os.path.join(a.dir, "*.wav"))):
        rid = os.path.basename(f)[:-4]
        if want and rid not in want:
            continue
        y, sr = sf.read(f, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(1)
        z, ok = trim(y, sr)
        if not ok:
            continue
        if abs(z).max() > 0.98:
            z = z * (0.98 / abs(z).max())
        sf.write(f, z, sr, subtype="PCM_16")
        n += 1
        saved += (len(y) - len(z)) / sr
    print("掐边 %d 条，共省 %.1f 秒" % (n, saved))


if __name__ == "__main__":
    main()
