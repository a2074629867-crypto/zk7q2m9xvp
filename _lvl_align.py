# -*- coding: utf-8 -*-
"""_lvl_align.py —— 把一目录的 wav 统一到 voiced RMS −24dBFS（跨度目标 ≤1dB）。

为什么需要（2026-11-15 13:0x 实测）：
  `mt_final_pause.py` **不做**成品响度归一化（它只把底噪 bed 抬到 −58dB），
  交付电平直接继承 dots.tts 的直出电平 ⇒ 对白 239 条实测
  中位 −23.68、p05 −24.00、p95 −22.85、min −24.24、max −21.79，**跨度 2.45dB**，
  21 条落在 −25~−23 之外。用户要求是「全库 −24dBFS、跨度 ≤1dB」。

口径与 `_sweep_norm.py` / 旁白侧完全一致：
  voiced RMS → −24.0dBFS；峰值超 0.97 时按峰值回退（宁低不削波）。

用法：
  G:/Python310/python.exe -u _lvl_align.py --dir _audio_ch123/out_paused --dry
  G:/Python310/python.exe -u _lvl_align.py --dir _audio_ch123/out_paused --apply
"""
import argparse
import glob
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db  # noqa: E402

TARGET = -24.0
PEAK_CAP = 0.97


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--peak-cap", type=float, default=PEAK_CAP)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", default="")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    rows = []
    for p in files:
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        lv, _, _ = voiced_db(y, sr)
        rows.append([p, lv, float(np.abs(y).max()), sr])
    vs = [r[1] for r in rows if r[1] is not None]
    print("n=%d  中位 %.2f  min %.2f  max %.2f  跨度 %.2f  越界(−25~−23) %d" % (
        len(rows), float(np.median(vs)), min(vs), max(vs), max(vs) - min(vs),
        sum(1 for v in vs if not (-25 <= v <= -23))))

    if not a.apply:
        need = [(os.path.basename(r[0]), r[1], a.target - r[1]) for r in rows
                if r[1] is not None and abs(r[1] - a.target) > 0.25]
        print("需要调整 %d 条（阈值 ±0.25dB）；示例：" % len(need))
        for n, lv, d in need[:8]:
            print("   %-12s %.2f → %+0.2f dB" % (n, lv, d))
        return 0

    if a.backup:
        os.makedirs(a.backup, exist_ok=True)
        for r in rows:
            shutil.copy2(r[0], os.path.join(a.backup, os.path.basename(r[0])))
        print("已备份到", a.backup)

    log, capped = [], 0
    for p, lv, pk, sr in rows:
        if lv is None or not np.isfinite(lv):
            continue
        g = 10 ** ((a.target - lv) / 20.0)
        if pk * g > a.peak_cap:
            g = a.peak_cap / max(1e-9, pk)
            capped += 1
        if abs(20 * np.log10(g)) < 0.05:
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y2 = (np.ascontiguousarray(y) * g).astype("float32")
        sf.write(p, y2, sr, subtype="PCM_16")
        log.append(dict(id=os.path.basename(p)[:-4], before=round(lv, 2),
                        gain=round(20 * np.log10(g), 2)))
    print("实际调整 %d 条，峰值受限 %d 条" % (len(log), capped))

    rows2 = []
    for p in files:
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        lv, _, _ = voiced_db(np.ascontiguousarray(y), sr)
        if lv is not None:
            rows2.append(lv)
    print("归一后 中位 %.2f  min %.2f  max %.2f  跨度 %.2f  越界 %d" % (
        float(np.median(rows2)), min(rows2), max(rows2), max(rows2) - min(rows2),
        sum(1 for v in rows2 if not (-25 <= v <= -23))))
    out = os.path.join(a.dir, "_lvl_align_log.json")
    json.dump(log, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("台账", out)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
