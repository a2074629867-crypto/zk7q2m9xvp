# -*- coding: utf-8 -*-
"""c2_0191 整句 F0 曲线对比：为什么「整条曲线」都不如三档版。

设计原则（对应 PROSODY_ACTION.md R1/R2）：
  * 只比 F0，不碰停顿/语速/时长
  * 一律句内自归一（相对句中位），跨版本才可比
  * 输出布尔/分布量，不打综合分

六个量：
  TV      帧间 |Δst| 总和 / 句长（每秒半音抖动）—— 曲线毛不毛
  rho     词级 F0 与时间序的 Spearman —— 整句有没有在降（陈述句该显著为负）
  resid   downstep 模型（峰 i+1 = 峰 i + 常数）拟合残差 SD —— 忽高忽低
  span    词级 F0 p95-p5（st）—— 音域
  oct     帧间跳 >10st 的次数（人声做不到，会被误读成重音）
  step    相邻词 |Δst| 的中位 / 最大
"""
import io
import json
import os
import sys

import librosa
import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SID = "c2_0191"
COMBOS = [
    ("old", os.path.join(ROOT, "_audio_ch123/out", SID + ".wav"),
     os.path.join(ROOT, "_accent_fix_old.jsonl")),
    ("new", os.path.join(ROOT, "_regen_final", SID + ".wav"),
     os.path.join(ROOT, "_accent_fix_new.jsonl")),
]
SR16 = 16000
HOP = 160          # 10ms
OCT_ST = 10.0      # 人声做不到的帧间跳变阈值（US7286986 定性）


def f0_frames(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y16 = librosa.resample(y, orig_sr=sr, target_sr=SR16)
    f0, vflag, _ = librosa.pyin(y16, fmin=60, fmax=400, sr=SR16,
                                frame_length=1024, hop_length=HOP)
    t = np.arange(len(f0)) * HOP / float(SR16)
    ok = vflag & np.isfinite(f0)
    return t, f0, ok, len(y) / float(sr)


def to_st(f0):
    return 12.0 * np.log2(np.asarray(f0, dtype=float) / 100.0)


def words_of(jsonl, sid):
    for l in io.open(jsonl, encoding="utf-8"):
        r = json.loads(l)
        if r["id"] == sid:
            return r["words"]
    return []


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d > 0 else 0.0


def analyse(path, words):
    t, f0, ok, dur = f0_frames(path)
    st = to_st(f0)

    # 1) 帧级抖动：只统计连续有声帧
    d = []
    prev = None
    for i in range(len(st)):
        if not ok[i]:
            prev = None
            continue
        if prev is not None:
            d.append(abs(st[i] - st[prev]))
        prev = i
    d = np.array(d) if d else np.array([0.0])
    voiced_sec = ok.sum() * HOP / float(SR16)
    TV = float(d.sum() / max(1e-3, voiced_sec))

    # 2) 八度跳变次数
    oct_n = int((d > OCT_ST).sum())

    # 3) 词级序列（用词 span 内有声帧的中位）
    seq = []
    for w in words:
        if w.get("p50") is None:
            continue
        m = ok & (t >= w["t0"]) & (t < w["t1"])
        if m.sum() < 2:
            continue
        v = st[m]
        seq.append(dict(w=w["w"], t0=w["t0"], t1=w["t1"],
                        med=float(np.median(v)),
                        lo=float(np.percentile(v, 10)),
                        hi=float(np.percentile(v, 90)),
                        pos=w.get("pos")))
    if len(seq) < 3:
        return dict(note="词级不足", TV=TV, oct=oct_n, dur=dur)

    meds = np.array([s["med"] for s in seq])
    meds0 = meds - np.median(meds)                      # 相对句中位
    tm = np.array([0.5 * (s["t0"] + s["t1"]) for s in seq])

    span = float(np.percentile(meds0, 95) - np.percentile(meds0, 5))
    rho = spearman(tm, meds0)

    # 4) downstep 模型残差：相邻词 Δst 的 SD（理想 downstep 是常数步长）
    steps = np.diff(meds0)
    resid = float(np.std(steps, ddof=1)) if len(steps) > 2 else 0.0

    return dict(TV=round(TV, 2), oct=oct_n, span=round(span, 2),
                rho=round(rho, 3), resid=round(resid, 2),
                step_med=round(float(np.median(np.abs(steps))), 2),
                step_max=round(float(np.max(np.abs(steps))), 2),
                dur=round(dur, 2), n_word=len(seq), seq=seq)


def main():
    out = {}
    for tag, wav, jl in COMBOS:
        if not os.path.exists(wav):
            print("缺", wav)
            continue
        ws = words_of(jl, SID)
        out[tag] = analyse(wav, ws)

    print("=== c2_0191 整句 F0 曲线 ===")
    print("%-4s %7s %4s %7s %8s %7s %7s %7s"
          % ("版", "TV", "oct", "span", "rho", "resid", "step中位", "step最大"))
    for tag in ("old", "new"):
        r = out.get(tag) or {}
        if not r:
            continue
        print("%-4s %7.2f %4d %7.2f %8.3f %7.2f %7.2f %7.2f"
              % (tag, r["TV"], r["oct"], r["span"], r["rho"],
                 r["resid"], r["step_med"], r["step_max"]))

    print()
    print("=== 逐词 F0 序列（st，相对句中位）===")
    for tag in ("old", "new"):
        r = out.get(tag) or {}
        seq = r.get("seq") if r else None
        if not seq:
            continue
        base = np.median([s["med"] for s in seq])
        print("--- %s ---" % tag)
        for s in seq:
            v = s["med"] - base
            bar = ("+" if v >= 0 else "-") * int(round(abs(v) * 2))
            print("  %-14s %5.2fs-%5.2fs  %+6.2fst  %s"
                  % (s["w"], s["t0"], s["t1"], v, bar))

    json.dump(out, io.open(os.path.join(ROOT, "_diag_c20191.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=1)
    print()
    print("→ G:/_setup/_diag_c20191.json")


if __name__ == "__main__":
    main()
