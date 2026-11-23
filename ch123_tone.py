# -*- coding: utf-8 -*-
"""语调体检：把一条音频按静音切成句，报每句 F0 中位 / 电平 / 语速，判定是否"语调断裂"。

用法：python ch123_tone.py 文件1.wav 文件2.wav ...
判据（Charles/Hooper 童声）：
  F0 跨度 > 50Hz  → 语调断裂（像换了人）
  末句 F0 < 全局中位 - 45Hz → 塌音区（"越说越小"的听感来源）
  wpm > 210  → 语速赶
  首尾有声电平差 > 3dB → 电平衰减
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import parselmouth
import soundfile as sf

import ch123_level as L
import ch123_rebuild as RB


def probe(path):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    s = parselmouth.Sound(a.astype(float), sampling_frequency=sr)
    pit = s.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    ts = pit.xs()
    fs = pit.selected_array["frequency"]
    rows = []
    for s0, s1 in segs:
        sel = [f for t, f in zip(ts, fs) if f > 0 and s0 <= t < s1]
        db = RB.rms_voiced_db(a[int(s0 * sr):int(s1 * sr)], sr)
        rows.append(dict(t0=s0, t1=s1, dur=s1 - s0, f0=float(np.median(sel)) if sel else 0.0, db=db, n=len(sel)))
    allf = [r["f0"] for r in rows if r["f0"] > 0]
    span = (max(allf) - min(allf)) if allf else 0.0
    med = float(np.median(allf)) if allf else 0.0
    tail_drop = med - rows[-1]["f0"] if rows else 0.0
    d = len(a) / sr
    return dict(path=path, dur=d, rows=rows, span=span, med=med, tail_drop=tail_drop,
                decay=L.decay_db(a, sr), head=rows[0]["t0"] if rows else 0,
                tail=d - rows[-1]["t1"] if rows else 0)


def report(r, words=None):
    name = os.path.basename(r["path"])
    flags = []
    if r["span"] > 50:
        flags.append("语调断裂")
    if r["tail_drop"] > 45:
        flags.append("塌音区")
    if r["decay"] > 3:
        flags.append("电平衰减")
    wpm = ("%.0f wpm" % (words / r["dur"] * 60)) if words else ""
    print("%-14s %5.2fs %-9s 跨度%4.0f 末句跌%4.0f 衰减%4.1f  %s"
          % (name, r["dur"], wpm, r["span"], r["tail_drop"], r["decay"], ("← " + "/".join(flags)) if flags else "OK"))
    print("      " + "  ".join("%.0fHz/%.0fdB" % (x["f0"], x["db"]) for x in r["rows"]))


if __name__ == "__main__":
    words = None
    args = sys.argv[1:]
    if args and args[0].startswith("--words="):
        words = int(args[0].split("=")[1])
        args = args[1:]
    for p in args:
        report(probe(p), words)
