# -*- coding: utf-8 -*-
"""建立「同精度、不同 seed」的韵律摆动基线（噪声上沿）。

为什么必须先跑这个（第 9 次同型教训）：
  bf16 与 q8_0 的输出一定不同 —— TTS 是采样生成，权重动一下采样轨迹就分叉。
  看到差异不能直接归因于量化。必须先把「同精度换 seed」的摆动量量出来，
  只有当 bf16-vs-q8 的差异 **超过 seed 摆动** 时，才能说量化伤了韵律。

指标（四个轴，都不依赖文本对齐）：
  dur      总时长
  vwpm     voiced wpm（只算发声帧）
  f0_iqr   F0 四分位距（半音），段级音域
  segs     语音段数（VAD 连断，反映单元内停顿时长，间接反映念标点的习惯）

用法：
  python _prec_noise.py --a _mt_raw_s42 --b _mt_raw_s1234 --n 60
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")

import numpy as np
import soundfile as sf

import mt_final_pause as FP

try:
    import parselmouth
    from parselmouth.praat import call
    HAVE_PM = True
except Exception:
    HAVE_PM = False


def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))


def f0_iqr_st(x, sr, floor=60.0, ceil=250.0):
    """F0 四分位距（半音）。只取 voiced 帧。

    用 to_pitch_ac（不是 praat call），这是本项目验证过的口径：
    floor 60 / ceil 250 / voicing 0.20，旁白 HNR 低，默认阈值只认 12% 的帧。
    """
    if not HAVE_PM or len(x) < sr // 4:
        return np.nan
    try:
        snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
        pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor,
                                pitch_ceiling=ceil, voicing_threshold=0.20)
    except Exception:
        return np.nan
    f = pitch.selected_array["frequency"]
    f = f[np.isfinite(f) & (f > 0)]
    if len(f) < 20:
        return np.nan
    st = 12 * np.log2(f / 55.0)
    return float(np.percentile(st, 75) - np.percentile(st, 25))


def measure(path, w):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    dur = len(x) / sr
    db, nfl, hop = FP.frame_db(x, sr)
    if len(db) == 0:
        return None
    on = db > (np.percentile(db, 90) - 25.0)
    voiced = float(on.sum()) * hop / sr
    if voiced < 0.2:
        return None
    # 段数：断开 >50ms 记一次
    idx = np.where(on)[0]
    nseg = 1 + int((np.diff(idx) > int(0.05 / 0.01)).sum()) if len(idx) > 1 else 1
    return dict(dur=dur, vwpm=w / voiced * 60, f0_iqr=f0_iqr_st(x, sr), segs=nseg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="_mt_raw_s42")
    ap.add_argument("--b", default="_mt_raw_s1234")
    ap.add_argument("--state", default="_mt_loop_state.json")
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--n", type=int, default=60, help="抽多少条（按词数分层，覆盖长短）")
    ap.add_argument("--out", default="_prec_noise.json")
    a = ap.parse_args()

    S = json.load(open(a.state, encoding="utf-8"))["units"]
    ks = sorted(k for k, v in S.items() if v.get("ch") == a.ch)
    # 按词数分层抽样：短/中/长各 1/3
    ks = [k for k in ks if os.path.exists(os.path.join(a.a, k + ".wav"))
          and os.path.exists(os.path.join(a.b, k + ".wav"))]
    ks.sort(key=lambda k: nwords(S[k]["text"]))
    step = max(1, len(ks) // a.n)
    sel = ks[::step][: a.n]

    rows = []
    for i, k in enumerate(sel):
        w = nwords(S[k]["text"])
        ma = measure(os.path.join(a.a, k + ".wav"), w)
        mb = measure(os.path.join(a.b, k + ".wav"), w)
        if not ma or not mb:
            continue
        rows.append(dict(uid=k, w=w, A=ma, B=mb))
        if (i + 1) % 10 == 0:
            print("  %d/%d" % (i + 1, len(sel)), flush=True)

    print("\n=== 同精度 · 不同 seed 的摆动（n=%d 条）===" % len(rows))
    print("%-10s %10s %10s %10s %10s" % ("指标", "中位", "p90|Δ|", "p90 相对", "max 相对"))
    out = {}
    for key, name in (("dur", "总时长 s"), ("vwpm", "voiced wpm"),
                      ("f0_iqr", "F0 IQR 半音"), ("segs", "语音段数")):
        A = np.array([r["A"][key] for r in rows], dtype=float)
        B = np.array([r["B"][key] for r in rows], dtype=float)
        ok = np.isfinite(A) & np.isfinite(B)
        A, B = A[ok], B[ok]
        if len(A) == 0:
            print("%-10s 无有效样本" % name)
            continue
        d = np.abs(A - B)
        rel = np.maximum(A, B) / np.maximum(np.minimum(A, B), 1e-9)
        med = float(np.median((A + B) / 2))
        out[key] = dict(median=med, p90_abs=float(np.percentile(d, 90)),
                        p90_rel=float(np.percentile(rel, 90)),
                        max_rel=float(rel.max()), n=int(len(A)))
        print("%-10s %10.3f %10.3f %10.3f %10.3f"
              % (name, med, np.percentile(d, 90), np.percentile(rel, 90), rel.max()))

    json.dump(dict(rows=rows, summary=out, A=a.a, B=a.b),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 " + a.out)
    print("\n判据：bf16-vs-q8 的差异若落在这个范围内，说明是采样随机性，不是量化损伤。")


if __name__ == "__main__":
    main()
