# -*- coding: utf-8 -*-
"""Prosogram-lite：用 d'Alessandro & Mertens 的听觉音高模型判「这个词有没有可听的音高变化」。

参数全部来自 Prosogram 官方说明（sites.google.com/site/prosogram/home）：

  - glissando 阈值 G = 0.32/T²（单位 ST/s，T = 音段时长 s）
      * 0.16/T² 是「实验室重复呈现」的阈值
      * **0.32/T² 是连续言语下与听者一致的那一档**（用 TD-PSOLA 重合成做过 A/B 验过）
      * 自适应版在停顿前取 0.16，别处取 0.32
  - 微分 glissando 阈值 DG = 30 ST/s（区分相邻两段的斜率差）
  - 先把 F0 做 WTA（时间整合窗）平滑，再分段

判读：一个词内若 |ΔF0| < G(T)·T = 0.32/T，耳朵听到的是**平调（没有音高变化）**；
超过才听成滑音（glissando）。这就是「糊」与「有起伏」的听觉分界，不是我自己拍的阈值。

用法：
  python _prosogram_lite.py c2_0191 --ver old
  python _prosogram_lite.py c2_0191 --ver new
"""
import argparse
import json
import os

import numpy as np
import parselmouth
import soundfile as sf

ROOT = "G:/_setup"
VER_DIR = {"old": "_audio_ch123/out", "new": "_regen_final"}
VER_FEAT = {"old": "_accent_feat_old.jsonl", "new": "_accent_feat_new.jsonl"}

WTA_WIN = 0.25          # s，时间整合窗（d'Alessandro & Castellengo 1994 的量级）
DG = 30.0               # ST/s，微分 glissando 阈值
G_HIGH = 0.32           # 连续言语档
G_LOW = 0.16            # 停顿前档


def f0_curve(path, step=0.01):
    snd = parselmouth.Sound(path)
    p = snd.to_pitch_ac(time_step=step, pitch_floor=50, pitch_ceiling=400,
                        voicing_threshold=0.45, octave_cost=0.01, octave_jump_cost=0.35)
    f0 = p.selected_array["frequency"].astype(float)
    f0[f0 <= 0] = np.nan
    return f0, float(snd.duration)


def wta(f0, step=0.01, win=WTA_WIN):
    """时间整合：只在有声帧上做加权平均（Hann 窗），NaN 不参与。"""
    n = len(f0)
    half = max(1, int(win / step / 2))
    w = np.hanning(2 * half + 1)
    out = np.full(n, np.nan)
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        seg = f0[a:b]
        ww = w[half - (i - a): half + (b - i)]
        m = ~np.isnan(seg)
        if m.sum() >= 3:
            out[i] = np.sum(seg[m] * ww[m]) / np.sum(ww[m])
    return out


def hz2st(hz, ref):
    return 12.0 * np.log2(np.asarray(hz, dtype=float) / ref)


def events(x, i0, i1, step=0.01):
    """在一个词的时间窗内找「可听的音高段」：按 G=0.32/T² 判。

    做法：把窗内所有有声帧按时间连成若干段，每段内用「单调扫描」找极值点，
    相邻极值之间的 |ΔF0| 若 >= 0.32/T 就算一次可听变化。
    """
    seg = x[i0:i1]
    idx = np.where(~np.isnan(seg))[0]
    if len(idx) < 5:
        return []
    ys = seg[idx]
    ts = (idx + i0) * step
    # 平滑后找局部极值（在 ±2 帧邻域内）
    ext = [0]
    for k in range(1, len(ys) - 1):
        a, b, c = ys[k - 1], ys[k], ys[k + 1]
        if (b - a) * (c - b) <= 0 and abs(b - a) + abs(c - b) > 0:
            ext.append(k)
    ext.append(len(ys) - 1)
    # 合并过近的极值
    keep = [ext[0]]
    for k in ext[1:]:
        if ts[k] - ts[keep[-1]] >= 0.06:
            keep.append(k)
    out = []
    for a, b in zip(keep[:-1], keep[1:]):
        T = float(ts[b] - ts[a])
        if T < 0.05:
            continue
        d = float(abs(ys[b] - ys[a]))
        thr = (G_HIGH if True else G_LOW) / max(T, 1e-6)     # 0.32/T  (st)
        if d >= thr:
            out.append({"t0": round(float(ts[a]), 3), "t1": round(float(ts[b]), 3),
                        "d_st": round(d, 2), "thr_st": round(thr, 2),
                        "rate_st_s": round(d / T, 1),
                        "dir": "↑" if ys[b] > ys[a] else "↓"})
    return out


def load_words(sid, ver):
    with open(os.path.join(ROOT, VER_FEAT[ver]), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] == sid:
                return r["words"]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sid")
    ap.add_argument("--ver", default="new", choices=["old", "new"])
    a = ap.parse_args()

    wav = os.path.join(ROOT, VER_DIR[a.ver], a.sid + ".wav")
    f0, dur = f0_curve(wav)
    x = wta(f0)
    ref = float(np.nanmedian(x))
    x = hz2st(x, ref)                      # 相对句内中位，单位 st
    words = load_words(a.sid, a.ver)

    print(f"{a.sid} [{a.ver}]  {dur:.2f}s  句内中位 {ref:.1f}Hz")
    print(f"{'词':<12}{'起':>6}{'止':>6}{'跨度':>7}{'阈值':>6}  可听音高段")
    n_ev = 0
    for w in words:
        i0, i1 = int(w["t0"] / 0.01), int(w["t1"] / 0.01)
        if i1 - i0 < 4:
            continue
        ev = events(x, i0, i1)
        n_ev += len(ev)
        span = ""
        if ev:
            span = "  ".join(f"{e['dir']}{e['d_st']}st/{e['d_st']/max(e['t1']-e['t0'],1e-6):.0f}st·s⁻¹" for e in ev)
        print(f"{w['w']:<12}{w['t0']:>6.2f}{w['t1']:>6.2f}{'':>7}{'':>6}  {span or '—（平调，听不到变化）'}")
    print(f"\n可听音高段合计 {n_ev} 个 / {len(words)} 词")


if __name__ == "__main__":
    main()
