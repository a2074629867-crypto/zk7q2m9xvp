# -*- coding: utf-8 -*-
"""_backfill3.py —— 通用回填（id→源文件 JSON），写 out 与 out_paused 两份

与原 `_backfill2.py` 同一套电平规则（voiced RMS 归一到 −24 dBFS，peak 限 0.97），
区别是 picks 从 JSON 读，能一次回填一批，且备份目录可指定。

用法：
  G:/Python310/python.exe _backfill3.py --picks _pick52_sel.json \
      --bak G:/_setup/_bak_native_1120
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db

DIRS = ["G:/_setup/_audio_ch123/out", "G:/_setup/_audio_ch123/out_paused"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", required=True, help='JSON {"c2_0246":"path/to.wav", ...}')
    ap.add_argument("--bak", default="G:/_setup/_bak_native_1120")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    picks = json.load(open(a.picks, encoding="utf-8"))
    os.makedirs(a.bak, exist_ok=True)
    done = {}
    for rid, src in picks.items():
        if not os.path.exists(src):
            print("缺文件 %s <- %s" % (rid, src))
            continue
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y.astype("float32"))
        lv, _, _ = voiced_db(y, sr)
        if lv is None or abs(lv + 24.0) > 0.35:
            g = 10 ** ((-24.0 - lv) / 20.0) if lv else 1.0
            y = (y * g).astype("float32")
            if float(np.abs(y).max()) > 0.97:
                y = (y * (0.97 / float(np.abs(y).max()))).astype("float32")
            lv, _, _ = voiced_db(y, sr)
        if not a.dry:
            for d in DIRS:
                dst = os.path.join(d, rid + ".wav")
                if os.path.exists(dst):
                    shutil.copy2(dst, os.path.join(a.bak, os.path.basename(d) + "_" + rid + ".wav"))
                sf.write(dst, y, sr, subtype="PCM_16")
        done[rid] = dict(src=src, dur=round(len(y) / sr, 3),
                         rms=round(float(lv), 2) if lv else None)
        print("%-9s <- %-30s dur %.2f rms %.2f%s"
              % (rid, os.path.basename(src), len(y) / sr, lv if lv else 0,
                 "  (dry)" if a.dry else ""))
    p = "G:/_setup/_backfill_native.json"
    old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    old.update(done)
    json.dump(old, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("回填 %d 条，备份在 %s" % (len(done), a.bak))


if __name__ == "__main__":
    main()
