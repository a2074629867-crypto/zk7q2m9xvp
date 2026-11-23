# -*- coding: utf-8 -*-
"""检测参考音频里有没有配乐/背景音乐（2026-11-21 用户指出 Helena/Joseph 参考带电影配乐）。

原理：人声录音的停顿处应该只剩底噪（相对语音峰值 −45 dB 以下）。
如果停顿处仍有 −30 dB 左右的持续能量，而且这些能量是**谐波性**的
（谱平坦度低、自相关有周期峰），那就不是噪声而是音乐。

三个量：
  gap_db   —— 语音段之后的「停顿」相对语音段的电平差（越大越干净）
  flat     —— 停顿段的谱平坦度中位（音乐 ~0.0x，白噪 ~0.5）
  period   —— 停顿段自相关最大值（音乐有节拍/基频 → 高）
"""
import argparse
import glob
import json
import io
import os
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SR = 16000
FL = int(0.032 * SR)      # 32ms 帧
HOP = int(0.010 * SR)


def load16(path):
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    if sr != SR:
        n = int(len(y) * SR / sr)
        y = np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y).astype("float32")
    return y


def frames(y):
    n = 1 + (len(y) - FL) // HOP
    if n < 2:
        return None
    idx = np.arange(FL)[None, :] + HOP * np.arange(n)[:, None]
    return y[idx]


def analyze(y):
    fr = frames(y)
    if fr is None:
        return None
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    # 语音阈值：峰值下 30 dB 以内算有声
    thr = db.max() - 30.0
    voiced = db > thr
    if voiced.sum() < 5 or (~voiced).sum() < 5:
        return None

    # 谱平坦度（几何均值/算术均值）
    win = np.hanning(FL).astype("float32")
    S = np.abs(np.fft.rfft(fr * win, axis=1)) + 1e-10
    flat = np.exp(np.log(S).mean(1)) / S.mean(1)

    # 自相关峰（判断周期性 = 有音高）
    def ac_peak(seg):
        s = seg - seg.mean()
        if np.sqrt((s ** 2).mean()) < 1e-6:
            return 0.0
        r = np.correlate(s, s, "full")[len(s) - 1:]
        if r[0] <= 0:
            return 0.0
        r = r / r[0]
        lo, hi = int(SR / 400), min(len(r) - 1, int(SR / 60))   # 60~400Hz
        if hi <= lo + 2:
            return 0.0
        return float(np.max(r[lo:hi]))

    gap_idx = np.where(~voiced)[0]
    # 只看「句子之间」的停顿：连续 ≥100ms 的非有声段，且不在文件首尾 0.3s 内
    runs, s = [], None
    for k in range(len(voiced)):
        if not voiced[k] and s is None:
            s = k
        if voiced[k] and s is not None:
            runs.append((s, k))
            s = None
    if s is not None:
        runs.append((s, len(voiced)))
    runs = [r for r in runs if (r[1] - r[0]) * HOP / SR >= 0.10]
    edge = int(0.3 * SR / HOP)
    runs = [r for r in runs if r[0] > edge and r[1] < len(voiced) - edge]
    if not runs:
        return None

    gdb = np.concatenate([db[a:b] for a, b in runs])
    gflat = np.concatenate([flat[a:b] for a, b in runs])
    vdb = db[voiced]
    # 每个停顿帧的自相关峰（抽样，最多 60 帧，控制耗时）
    sel = np.linspace(0, len(fr) - 1, min(60, len(fr))).astype(int)
    sel = [i for i in sel if not voiced[i]]
    pers = [ac_peak(fr[i]) for i in sel] or [0.0]

    return {
        "dur": round(len(y) / SR, 2),
        "voiced_med": round(float(np.median(vdb)), 1),
        "gap_med": round(float(np.median(gdb)), 1),
        "gap_db": round(float(np.median(vdb) - np.median(gdb)), 1),
        "flat": round(float(np.median(gflat)), 4),
        "period": round(float(np.median(pers)), 3),
        "gap_sec": round(float(len(gdb) * HOP / SR), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_ref9")
    ap.add_argument("--glob", default="*.wav")
    ap.add_argument("--out", default="_music_probe.json")
    a = ap.parse_args()

    d = a.dir if os.path.isabs(a.dir) else os.path.join(ROOT, a.dir)
    files = sorted(glob.glob(os.path.join(d, a.glob)))
    rows = {}
    print("%-26s %6s %7s %7s %6s %6s  %s" % ("file", "dur", "gap_db", "gap_med", "flat", "period", "判定"))
    for f in files:
        try:
            m = analyze(load16(f))
        except Exception as e:
            print("%-26s ERR %s" % (os.path.basename(f), e))
            continue
        if not m:
            continue
        # 判定：停顿处电平高于语音 −32 dB（gap_db < 32）且有谐波性 → 有配乐
        susp = m["gap_db"] < 32
        harm = m["period"] > 0.30 or m["flat"] < 0.02
        tag = "MUSIC?" if (susp and harm) else ("noisy?" if susp else "clean")
        m["verdict"] = tag
        rows[os.path.basename(f)] = m
        print("%-26s %6.2f %7.1f %7.1f %6.3f %6.2f  %s" % (
            os.path.basename(f), m["dur"], m["gap_db"], m["gap_med"], m["flat"], m["period"], tag))

    json.dump(rows, io.open(os.path.join(ROOT, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    bad = [k for k, v in rows.items() if v["verdict"] != "clean"]
    print("\n可疑 %d / %d: %s" % (len(bad), len(rows), bad))


if __name__ == "__main__":
    main()
