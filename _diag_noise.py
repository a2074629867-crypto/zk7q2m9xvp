# -*- coding: utf-8 -*-
"""噪声 / 静音 / 拼接硬切 诊断：给定 wav，逐段量化「除噪干不干净」。

判据（与 _scan_falsetail2.py 一致的数字零、静音缺口口径）：
- 数字零采样：人声不可能出现 abs(y)==0，出现即伪影
- 非语音段噪底：静音缺口里能量的 dBFS，干净应 < -65
- 缺口边缘：进入/离开静音的能量斜率，硬切会 > 60 dB / 10ms
- 稳态配乐残留：低能帧之间谱形相似度（配乐稳态 vs 噪声随机）
"""
import io
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def frames(y, sr, win=0.02, hop=0.005):
    n = int(win * sr)
    h = int(hop * sr)
    if len(y) < n:
        return np.zeros((0, n)), n, h
    cnt = 1 + (len(y) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(cnt)[:, None]
    return y[idx], n, h


def analyze(path, text=""):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    out = {"path": path, "sr": sr, "dur": round(len(y) / sr, 3),
           "peak": round(float(np.max(np.abs(y))), 4)}

    # --- 数字零 ---
    z = np.flatnonzero(np.abs(y) == 0.0)
    if len(z):
        runs = np.split(z, np.flatnonzero(np.diff(z) != 1) + 1)
        long_runs = [len(r) for r in runs if len(r) / sr >= 0.010]
        out["zero_samples"] = int(len(z))
        out["zero_runs_ge10ms"] = long_runs
        out["zero_runs_ge10ms_ms"] = [round(1000 * L / sr, 1) for L in long_runs]
        out["zero_head_ms"] = round(1000 * len(runs[0]) / sr, 1) if len(runs) else 0
        out["zero_tail_ms"] = round(1000 * len(runs[-1]) / sr, 1) if len(runs) else 0
    else:
        out["zero_samples"] = 0
        out["zero_runs_ge10ms"] = []

    # --- 逐帧能量 ---
    F, n, h = frames(y, sr)
    if len(F) == 0:
        return out
    w = np.hanning(n)
    rms = np.sqrt((F ** 2 * w).sum(1) / w.sum())
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    out["db_p95"] = round(float(np.percentile(db, 95)), 1)
    out["db_p50"] = round(float(np.percentile(db, 50)), 1)
    # 语音帧阈值：相对最响帧 -35dB
    thr = out["db_p95"] - 35.0
    out["thr"] = round(thr, 1)
    silent = db < thr

    # --- 静音缺口（>=80ms） ---
    gaps = []
    i = 0
    N = len(silent)
    while i < N:
        if silent[i]:
            j = i
            while j < N and silent[j]:
                j += 1
            d = (j - i) * h / sr
            if d >= 0.080:
                seg = db[i:j]
                gaps.append({
                    "t0": round(i * h / sr, 3),
                    "t1": round(j * h / sr, 3),
                    "ms": round(d * 1000),
                    "floor_db": round(float(np.min(seg)), 1),
                    "mean_db": round(float(np.mean(seg)), 1),
                })
            i = j
        else:
            i += 1
    out["gaps"] = gaps

    # --- 缺口边缘的硬切（10ms 内跳变 > 45dB） ---
    hard = []
    for g in gaps:
        i0 = int(g["t0"] * sr / h)
        i1 = int(g["t1"] * sr / h)
        if i0 > 2:
            rise = db[min(i0 + 2, N - 1)] - db[max(i0 - 1, 0)]
            if rise > 45:
                hard.append({"at": g["t0"], "dir": "in", "jump_db": round(float(rise), 1)})
        if i1 < N - 2:
            fall = db[min(i1 + 2, N - 1)] - db[max(i1 - 1, 0)]
            if fall < -45:
                hard.append({"at": g["t1"], "dir": "out", "jump_db": round(float(fall), 1)})
    out["hard_cuts"] = hard

    # --- 稳态残留检测：低能帧谱形一致性 ---
    sp = np.abs(np.fft.rfft(F * w, axis=1)) + 1e-12
    freqs = np.fft.rfftfreq(n, 1 / sr)
    lowmask = (freqs > 200) & (freqs < 4000)
    low = db < thr
    if low.sum() >= 5:
        prof = sp[low][:, lowmask]
        prof = prof / prof.sum(1, keepdims=True)
        med = np.median(prof, 0)
        corr = (prof * med).sum(1) / (np.linalg.norm(prof, axis=1) * np.linalg.norm(med) + 1e-12)
        pk = (freqs[lowmask][np.argmax(med)])
        out["quiet_frames"] = int(low.sum())
        out["quiet_floor_db"] = round(float(np.median(db[low])), 1)
        out["quiet_spectral_consistency"] = round(float(np.median(corr)), 3)
        out["quiet_peak_hz"] = int(pk)
        # 1-2kHz 占比（假尾伪影特征）
        fl = freqs[lowmask]
        m12 = (fl >= 1000) & (fl < 2000)
        out["quiet_1_2k_ratio"] = round(float(med[m12].sum() / med.sum()), 3)
    else:
        out["quiet_frames"] = int(low.sum())

    # --- 首尾 ---
    out["head_ms"] = round(float(np.argmax(np.abs(y) > 10 ** (-45 / 20))) / sr * 1000, 1)
    nz = np.flatnonzero(np.abs(y) > 10 ** (-45 / 20))
    out["tail_ms"] = round(float((len(y) - nz[-1] - 1) / sr * 1000), 1) if len(nz) else None
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    res = {}
    for f in a.files:
        r = analyze(f)
        res[os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f)] = r
        print(f"\n=== {f}")
        for k in ("dur", "peak", "db_p95", "thr", "zero_samples", "zero_runs_ge10ms_ms",
                  "head_ms", "tail_ms", "quiet_frames", "quiet_floor_db",
                  "quiet_spectral_consistency", "quiet_peak_hz", "quiet_1_2k_ratio"):
            if k in r:
                print(f"  {k:28s} {r[k]}")
        print(f"  gaps {len(r.get('gaps', []))}:")
        for g in r.get("gaps", []):
            print(f"    {g['t0']:6.2f}-{g['t1']:6.2f}  {g['ms']:4d}ms  floor {g['floor_db']:7.1f}dB  mean {g['mean_db']:7.1f}dB")
        if r.get("hard_cuts"):
            print(f"  HARD CUTS {r['hard_cuts']}")
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n-> " + a.json)


if __name__ == "__main__":
    main()
