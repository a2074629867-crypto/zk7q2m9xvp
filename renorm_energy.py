# -*- coding: utf-8 -*-
"""按**能量平均 voiced RMS** 把指定条目归一到 −24dBFS。

为什么不用 `ch123_clean.py`：它的 `RB.rms_voiced_db` 是算术平均 dB
（名字里带 rms 但没做均方根），用它归一出来的「−24」实际能量平均约 −18dBFS。
全库 716 条的实测中位是能量平均 −24.2，所以修单条也必须用同一把尺子。

用法：
  python renorm_energy.py --ids c1_0004,c2_0317 --dry
  python renorm_energy.py --ids c1_0004,c2_0317
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db  # noqa: E402

OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/_setup/_audio_ch123/out_bak_renorm"
TARGET = -24.0
PEAK_MAX = 0.891          # 需求 3：峰值 ≤ −1dBFS
LOG = "G:/_setup/_renorm_log.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    os.makedirs(BAK, exist_ok=True)
    log = []
    for k in ids:
        src = os.path.join(OUT, k + ".wav")
        if not os.path.exists(src):
            print("%-9s 不存在" % k)
            continue
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        lv0, _, _ = voiced_db(y, sr)
        pk0 = float(np.abs(y).max())
        gain_db = TARGET - lv0
        y2 = y * (10 ** (gain_db / 20.0))
        pk1 = float(np.abs(y2).max())
        clipped = False
        if pk1 > PEAK_MAX:                 # 宁可整体回退，不压瞬态
            y2 = y2 * (PEAK_MAX / pk1)
            clipped = True
        lv1, _, _ = voiced_db(y2, sr)
        pk2 = float(np.abs(y2).max())
        print("%-9s  %.1f → %.1f dBFS (增益 %+.1fdB)  峰值 %.3f → %.3f%s"
              % (k, lv0, lv1, gain_db, pk0, pk2, "  [峰值回退]" if clipped else ""))
        if not a.dry:
            shutil.copy2(src, os.path.join(BAK, k + ".wav"))
            sf.write(src, y2.astype(np.float32), sr, subtype="PCM_16")
            # 写完复核
            y3, _ = sf.read(src, dtype="float32")
            if y3.ndim > 1:
                y3 = y3.mean(1)
            lv3, _, _ = voiced_db(y3, sr)
            log.append(dict(id=k, before=round(lv0, 2), after=round(lv3, 2),
                            gain_db=round(gain_db, 2), peak=round(pk2, 3),
                            peak_rollback=clipped, backup=os.path.join(BAK, k + ".wav")))
            print("           落盘复核 %.1f dBFS" % lv3)

    if not a.dry:
        old = []
        if os.path.exists(LOG):
            old = json.load(open(LOG, encoding="utf-8"))
        json.dump(old + log, open(LOG, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n%d 条已归一，台账 %s" % (len(log), LOG))


if __name__ == "__main__":
    main()
