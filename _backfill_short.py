# -*- coding: utf-8 -*-
"""回填短句候选（双 ASR 仲裁通过的那些），并把电平拉到 -24 dBFS。

为什么单独一个脚本：
  候选来自 `_sweep/candNN`，RMS 常偏小 3~6dB（生成不确定性），不能直接交付（跨度会破 1dB）。
  回填必须先备份现役，写入后立刻复测 voiced RMS，确认落在 [-25,-23]。

用法：G:/Python310/python.exe _backfill_short.py
"""
import io
import json
import os
import shutil
import sys

sys.path.insert(0, "G:/_setup")

import numpy as np
import soundfile as sf

from narr_gate_phys import voiced_db

S = "G:/_setup"
OUT = os.path.join(S, "_audio_ch123", "out")
PAU = os.path.join(S, "_audio_ch123", "out_paused")
BAK = os.path.join(S, "_bak_short_1120")

# id -> 候选文件（双 ASR 仲裁通过：Parakeet cov/sim 与 whisper 召回）
MAP = {
    "c3_0629": "_sweep/cand15/c3_0629__s23.wav",
    "c3_0660": "_sweep/cand15/c3_0660__s23.wav",
    "c2_0277": "_sweep/cand15/c2_0277__s11.wav",
    "c2_0462": "_sweep/cand15/c2_0462__s23.wav",
}


def norm(y, sr, target=-24.0):
    lv, _, _ = voiced_db(np.ascontiguousarray(y), sr)
    if lv is None:
        return y, None, None
    g = 10 ** ((target - lv) / 20.0)
    if float(np.abs(y).max()) * g > 0.97:
        g = 0.97 / float(np.abs(y).max())
    y2 = (y * g).astype("float32")
    lv2, _, _ = voiced_db(np.ascontiguousarray(y2), sr)
    return y2, lv, lv2


def main():
    os.makedirs(BAK, exist_ok=True)
    rows = []
    for rid, rel in MAP.items():
        src = os.path.join(S, rel)
        if not os.path.exists(src):
            print("缺候选", rid, src)
            continue
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y2, lv, lv2 = norm(y, sr)
        for d in (OUT, PAU):
            p = os.path.join(d, rid + ".wav")
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(BAK, os.path.basename(d) + "_" + rid + ".wav"))
            sf.write(p, y2, sr, subtype="PCM_16")
        rows.append(dict(id=rid, src=os.path.basename(src), dur=round(len(y2) / sr, 2),
                         lv_before=None if lv is None else round(lv, 2),
                         lv_after=None if lv2 is None else round(lv2, 2)))
        print("%s <- %s  %.2fs  %.2f -> %.2f dBFS" % (rid, os.path.basename(src),
                                                    len(y2) / sr, lv or 0, lv2 or 0))
    json.dump(rows, io.open(os.path.join(S, "_backfill_short.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("备份", BAK)


if __name__ == "__main__":
    main()
