# -*- coding: utf-8 -*-
"""_f0_calib.py —— F0 高音帧判据标定（praat vs pyin，真人 vs 我们）。

要回答的问题
------------
`narr_check.verdict` 里 `n_hi >= 8 → FIX` 是死代码（在 `if fixes: return` 之后），
所以 211 条 `f0_hi_n>=8` 被静默吞掉。但**不能直接把阈值接回去**：
那条注释说「真人中位 0 / p90 0 / 最多 6 帧」是 2026-10-29 的口径，
而 2026-11-11 说「抽样复算 pyin 只在 1/3 条目复现」。两边都没落盘，无法追溯。

本脚本把尺子重新校一遍：
  1. 同一实现、同一参数，测**真人 159 条**（E:/ttsds/data/ref_human）与我们 716 条；
  2. 跟踪器换成 pyin 再测一遍 —— praat 在气声/嘎裂声上会八度错，pyin 概率模型更稳；
  3. 三个口径都算：
       hi_local  = 超**本条**中位 1.8x 的帧数（现判据用的，逐句中位会被八度污染）
       hi_global = 超**语料**中位 1.8x 的帧数（跨条统一基准）
       hi_ratio  = 高音帧占浊音帧比例（消时长影响，短句不被结构性压低）

先落 F0 轨迹到 npz，再一次算完 —— 不跑两遍 pyin。

用法
----
  G:/Python310/python.exe _f0_calib.py --n 12     # 小批试跑
  G:/Python310/python.exe _f0_calib.py --all      # 全量 875 条
"""
import argparse
import glob
import json
import os

import librosa
import numpy as np
import parselmouth

HUMAN = "E:/ttsds/data/ref_human/*.wav"
OURS = "G:/_setup/_audio_ch123/out/*.wav"
NPZ_H = "G:/_setup/_f0cal_human.npz"
NPZ_O = "G:/_setup/_f0cal_ours.npz"
OUT = "G:/_setup/_f0_calib.json"
REL = 1.8


def f0_praat(path):
    """完全复现 narr_check.py:179 的参数。"""
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=250,
                          voicing_threshold=0.45, silence_threshold=0.03)
    f = np.asarray(pit.selected_array["frequency"], dtype=float)
    return f[f > 0]


def f0_pyin(path):
    """概率跟踪器，16k 足够（fmax 250Hz），10ms 步长与 praat 对齐。"""
    y, sr = librosa.load(path, sr=16000, mono=True)
    f0, _, _ = librosa.pyin(y, fmin=60, fmax=250, sr=sr,
                            frame_length=1024, hop_length=160, fill_na=np.nan)
    return f0[~np.isnan(f0)]


def extract(pattern, tag, npz, n=None):
    fs = sorted(glob.glob(pattern))
    if n:
        step = max(1, len(fs) // n)
        fs = fs[::step][:n]
    names, arrs = [], []
    for i, p in enumerate(fs, 1):
        try:
            fp, fy = f0_praat(p), f0_pyin(p)
        except Exception as e:
            print("  !! %s %s" % (os.path.basename(p), e), flush=True)
            continue
        names.append(os.path.basename(p))
        arrs.append((fp, fy))
        if i % 20 == 0 or i == len(fs):
            print("  %s %d/%d" % (tag, i, len(fs)), flush=True)
    np.savez_compressed(npz, names=np.array(names),
                        **{"p_%d" % i: a[0] for i, a in enumerate(arrs)},
                        **{"y_%d" % i: a[1] for i, a in enumerate(arrs)})
    print("  → %s (%d 条)" % (npz, len(names)), flush=True)
    return names, arrs


def summarize(names, arrs, tag):
    meds = {"praat": [], "pyin": []}
    for fp, fy in arrs:
        if len(fp) >= 8:
            meds["praat"].append(float(np.median(fp)))
        if len(fy) >= 8:
            meds["pyin"].append(float(np.median(fy)))
    gmed = {k: round(float(np.median(v)), 1) for k, v in meds.items() if v}
    rows = []
    for nm, (fp, fy) in zip(names, arrs):
        r = {"unit": nm}
        for k, f in (("praat", fp), ("pyin", fy)):
            if len(f) < 8:
                r[k] = None
                continue
            med = float(np.median(f))
            r[k] = {
                "n": int(len(f)),
                "med": round(med, 1),
                "hi_local": int((f > REL * med).sum()),
                "hi_global": int((f > REL * gmed[k]).sum()),
                "hi_ratio": round(float((f > REL * gmed[k]).mean()), 4),
                "max": round(float(f.max()), 1),
            }
        rows.append(r)
    return {"tag": tag, "n": len(rows), "gmed": gmed, "rows": rows}


def dist(rows, key, field):
    v = [r[key][field] for r in rows if r.get(key)]
    if not v:
        return None
    s = sorted(v)
    q = lambda p: s[min(len(s) - 1, int(p * len(s)))]
    return {"n": len(s), "p50": q(.5), "p75": q(.75), "p90": q(.9), "p95": q(.95),
            "max": s[-1], "mean": round(float(np.mean(s)), 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    n = None if a.all else a.n
    nh, ah = extract(HUMAN, "真人", NPZ_H, n)
    no, ao = extract(OURS, "我们", NPZ_O, n)
    H = summarize(nh, ah, "human")
    O = summarize(no, ao, "ours")
    print("\n=== 真人 n=%d  全局中位 %s" % (H["n"], H["gmed"]))
    for k in ("praat", "pyin"):
        for fld in ("hi_local", "hi_global", "hi_ratio"):
            print("  %-6s %-10s %s" % (k, fld, dist(H["rows"], k, fld)))
    print("\n=== 我们 n=%d  全局中位 %s" % (O["n"], O["gmed"]))
    for k in ("praat", "pyin"):
        for fld in ("hi_local", "hi_global", "hi_ratio"):
            print("  %-6s %-10s %s" % (k, fld, dist(O["rows"], k, fld)))
    json.dump({"human": H, "ours": O}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n→", OUT)
