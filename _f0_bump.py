# -*- coding: utf-8 -*-
"""_f0_bump.py —— 只在指定词的区间上抬 F0 曲线，做「重音」，不动时长、不动音色。

原理：WORLD 声码器把语音拆成 f0（基频轨迹）/ sp（谱包络）/ ap（非周期成分）。
      只改 f0，sp/ap 原样送回合成 ⇒ 共振峰（=音色）完全不动，
      所以「换了个人」的风险从机制上就排除了，剩下的只是声码器本身的音质损失。

加重音的形状：不是台阶，是**升余弦驼峰**
    Δsemi(t) = A * 0.5*(1 - cos(2π (t-t0)/(t1-t0)))      t ∈ [t0, t1]
  驼峰两端斜率为 0 ⇒ 不会在词边界产生 F0 折角（折角听感是"电流声/咔哒"）。

用法：
    python _f0_bump.py --wav A.wav --prom A.prom --text "..." --adv carefully \
        --semi 3 --out B.wav [--head 0.03 --tail 0.10]
    python _f0_bump.py --self-test          # 只合成不抬升，测声码器透明度
"""
import argparse
import os
import sys

sys.path.insert(0, "G:/_setup")
import numpy as np
import pyworld as pw
import soundfile as sf

import _adv_align
import _f0_accent as F

FP = 5.0  # 帧移 ms


def span_of(text, prom, adv):
    rows = F.read_prom(prom)
    spans = _adv_align.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = _adv_align.text_words(text)
    idx = [i for i, t in enumerate(tw) if t["key"] == adv.lower()]
    if not idx:
        raise SystemExit("原文里找不到 %s" % adv)
    sp = spans[idx[-1]]
    if sp["t0"] is None:
        raise SystemExit("%s 没有对齐区间" % adv)
    return sp["t0"], sp["t1"]


def clean_f0(f0, win=9, th=5.0):
    """WORLD 的 harvest+stonemask 在低音区会出倍频错。用中值滤波剔除孤立跳变。"""
    v = f0 > 0
    if v.sum() < 30:
        return f0
    ref = float(np.median(f0[v]))
    st = np.full(len(f0), np.nan)
    st[v] = 12.0 * np.log2(f0[v] / ref)
    idx = np.where(v)[0]
    out = st.copy()
    h = win // 2
    for k in idx:
        a, b = max(idx[0], k - h), min(idx[-1], k + h)
        w = st[idx[(idx >= a) & (idx <= b)]]
        med = np.median(w)
        out[k] = med if abs(st[k] - med) > th else st[k]
    f2 = f0.copy()
    f2[v] = ref * 2.0 ** (out[v] / 12.0)
    return f2


def bump(f0, n_semi, t0, t1, head=0.03, tail=0.10, curve="hann"):
    """在 [t0-head, t1+tail] 上乘一个升余弦驼峰，返回新 f0 与被改的帧掩码。"""
    t = np.arange(len(f0)) * FP / 1000.0
    a, b = t0 - head, t1 + tail
    m = (t >= a) & (t <= b)
    if m.sum() < 3:
        return f0, m
    u = (t[m] - a) / max(1e-6, (b - a))
    if curve == "hann":
        w = 0.5 * (1 - np.cos(2 * np.pi * u))
    else:  # 平台：两侧各 15% 升余弦，中间平
        r = 0.15
        w = np.ones_like(u)
        w[u < r] = 0.5 * (1 - np.cos(np.pi * u[u < r] / r))
        w[u > 1 - r] = 0.5 * (1 - np.cos(np.pi * (1 - u[u > 1 - r]) / r))
    g = np.ones_like(f0)
    g[m] = 2.0 ** (n_semi * w / 12.0)
    out = f0.copy()
    v = f0 > 0
    out[v] *= g[v]
    return out, m


def run(wav, prom, text, adv, semi, out, head, tail, curve, clean=True):
    x, sr = sf.read(wav, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr < 16000:
        raise SystemExit("采样率太低 %d" % sr)
    f0, tt = pw.harvest(x, sr, f0_floor=60.0, f0_ceil=500.0, frame_period=FP)
    f0 = pw.stonemask(x, f0, tt, sr)
    if clean:
        f0 = clean_f0(f0)
    sp = pw.cheaptrick(x, f0, tt, sr)
    ap = pw.d4c(x, f0, tt, sr)
    t0, t1 = (None, None) if adv == "__none__" else span_of(text, prom, adv)
    if t0 is None:
        f0n, m = f0, np.zeros(len(f0), bool)
    else:
        f0n, m = bump(f0, semi, t0, t1, head, tail, curve)
    y = pw.synthesize(f0n, sp, ap, sr, frame_period=FP)
    y = np.asarray(y, dtype="float64")
    # 与原始等长 + 峰值不超
    n = min(len(y), len(x))
    y = y[:n]
    pk = np.abs(x).max()
    if np.abs(y).max() > 0.999 * max(pk, 1e-6):
        y *= 0.98 * pk / max(np.abs(y).max(), 1e-9)
    sf.write(out, y, sr)
    nz = int((f0 > 0).sum())
    print("  %s → %s  sr=%d  dur=%.2fs" % (os.path.basename(wav), os.path.basename(out), sr, n / sr))
    if t0 is not None:
        print("  词 %-12s 区间 [%.3f, %.3f]  驼峰 %+.1f 半音（%.3f→%.3f，%d 帧）"
              % (adv, t0, t1, semi, t0 - head, t1 + tail, int(m.sum())))
    print("  有声帧 %d/%d   F0 中位 %.1f Hz" % (nz, len(f0), np.median(f0[f0 > 0]) if nz else 0))
    return dict(t0=t0, t1=t1, frames=int(m.sum()), sr=sr, dur=n / sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=False)
    ap.add_argument("--prom", required=False)
    ap.add_argument("--text", default="")
    ap.add_argument("--adv", default="__none__")
    ap.add_argument("--semi", type=float, default=3.0)
    ap.add_argument("--out", required=False)
    ap.add_argument("--head", type=float, default=0.03)
    ap.add_argument("--tail", type=float, default=0.10)
    ap.add_argument("--curve", default="hann", choices=["hann", "flat"])
    ap.add_argument("--no-clean", action="store_true", help="不清洗 f0（对照用）")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        # 声码器透明度：f0 原样合成，测与原文件的差异
        run(a.wav, a.prom, a.text, "__none__", 0.0, a.out, 0, 0, a.curve, not a.no_clean)
        return
    if not (a.wav and a.out):
        ap.error("需要 --wav 和 --out")
    run(a.wav, a.prom, a.text, a.adv, a.semi, a.out, a.head, a.tail, a.curve, not a.no_clean)


if __name__ == "__main__":
    main()
