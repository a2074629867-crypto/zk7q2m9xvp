# -*- coding: utf-8 -*-
"""把选中的候选按全库同一套电平规范处理，回写进 ch123/。

用法：python ch123_apply.py L084=_fix79/L084_none_s47.wav L079=_fix79/L079_none_s48.wav
"""
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_tone as T
import ch123_unify as U

DST = "G:/_setup/ch123"


def main():
    for arg in sys.argv[1:]:
        key, src = arg.split("=", 1)
        a, sr = sf.read(src, dtype="float32", always_2d=True)
        a = a.mean(1)
        y = U.proc(a, sr)
        out = os.path.join(DST, key + ".wav")
        sf.write(out, y, sr, subtype="PCM_16")
        print("%-5s ← %-34s %5.2fs  %6.1f dBFS  peak %.2f" %
              (key, os.path.basename(src), len(y) / sr, RB.rms_voiced_db(y, sr),
               float(np.abs(y).max())))


if __name__ == "__main__":
    main()
