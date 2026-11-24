# -*- coding: utf-8 -*-
"""电平补偿：rubberband 拉伸会把 voiced RMS 拉低约 1.6dB，这里逐条补回 −24dBFS。

为什么单独一步而不并进 tempo：先量后补才准。ffmpeg 的 loudnorm 会改动态，
这里只用纯 volume 增益，峰值超 0.891 时按峰值封顶（红线）。

用法：
  G:/Python310/python.exe -u _level_fix.py --in _regen_1123_norm_paused --out _regen_final
  G:/Python310/python.exe -u _level_fix.py --in ... --out ... --dry
"""
import argparse
import io
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)
from narr_gate_phys import voiced_db  # noqa: E402

FF = "E:/tool/oopz/ffmpeg.exe"
TARGET = -24.0
PEAK_CAP = 0.891


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--report", default=os.path.join(ROOT, "_level_fix_report.json"))
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.inp) if f.endswith(".wav"))
    print("待处理 %d 条：%s -> %s" % (len(files), a.inp, a.out), flush=True)
    if not a.dry:
        os.makedirs(a.out, exist_ok=True)

    rows, done, fail = [], 0, 0
    for i, f in enumerate(files, 1):
        src = os.path.join(a.inp, f)
        dst = os.path.join(a.out, f)
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        lv, _, _ = voiced_db(y, sr)
        pk = float(np.abs(y).max())
        gain = a.target - lv
        if pk > 1e-6 and pk * (10 ** (gain / 20.0)) > PEAK_CAP:
            gain = 20.0 * np.log10(PEAK_CAP / pk)     # 按峰值封顶
        rows.append(dict(id=f[:-4], before=round(lv, 2), gain=round(float(gain), 2),
                         peak=round(pk, 3)))
        if not a.dry:
            tmp = dst + ".tmp.wav"
            cmd = [FF, "-y", "-v", "error", "-i", src,
                   "-af", "volume=%.3fdB" % gain, "-ac", "1", "-c:a", "pcm_s16le", tmp]
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0:
                os.replace(tmp, dst)
                done += 1
            else:
                print("   !! %s %s" % (f, r.stderr.decode("utf-8", "ignore")[:200]))
                fail += 1
        if i % 100 == 0:
            print("   %d/%d" % (i, len(files)), flush=True)

    g = [r["gain"] for r in rows]
    print()
    print("增益：中位 %+.2f dB  范围 %+.2f ~ %+.2f" % (float(np.median(g)), min(g), max(g)))
    print("补偿前 voiced RMS：中位 %.2f  跨度 %.2f dB"
          % (float(np.median([r["before"] for r in rows])),
             max(r["before"] for r in rows) - min(r["before"] for r in rows)))
    if not a.dry:
        print("落地 %d 条（失败 %d）" % (done, fail))
    json.dump(rows, io.open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("明细 → %s" % a.report)


if __name__ == "__main__":
    main()
