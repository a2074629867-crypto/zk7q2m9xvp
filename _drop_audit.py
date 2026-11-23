# -*- coding: utf-8 -*-
"""_drop_audit.py —— 把「曾经用过、后来被我判死」的指标重新拉出来对账。

回答的问题不是「它好不好」，而是：
  这个指标对**它本该抓的那类缺陷**到底有没有响应？
  响应幅度 vs 同批正常 take 的跨 seed 抖动 = 能不能单条判。

数据：
  好样本  G:/_setup/_mt_pick/{N0194,N0239,N0254,N0552,N0755}.wav
  坏样本  G:/_setup/_nat_deg/<uid>_<deg>.wav（8 类，各 5 条）
  抖动    G:/_setup/_mt_adv_ctl_*/<uid>.wav（同 uid、不同 seed、无标签）

输出 _drop_audit.json / _drop_audit.md
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = "G:/_setup"
PICK = os.path.join(HERE, "_mt_pick")
DEG = os.path.join(HERE, "_nat_deg")
UIDS = ["N0194", "N0239", "N0254", "N0552", "N0755"]
DEGS = ["chop", "clip", "flatamp", "hole", "jitter", "lowpass", "mono", "stutter"]


def read(p):
    x, sr = sf.read(p)
    if x.ndim > 1:
        x = x.mean(1)
    return x.astype(np.float64), sr


def pitch(x, sr, floor=60.0, ceil=400.0, vt=0.20):
    import parselmouth
    s = parselmouth.Sound(x, sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                      voicing_threshold=vt)
    f = p.selected_array["frequency"].astype(float)
    return f


def robust_f0(f):
    """剔八度错：迭代砍掉 >2.2x 中位的帧。"""
    v = f[f > 0]
    if len(v) < 5:
        return v
    for _ in range(3):
        m = np.median(v)
        if m <= 0:
            break
        keep = v[(v > m / 2.2) & (v < m * 2.2)]
        if len(keep) == len(v):
            break
        v = keep
    return v


def frame_db(x, sr, fl=0.02, hop=0.01):
    n, h = int(fl * sr), int(hop * sr)
    if len(x) < n:
        return np.array([20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)])
    k = 1 + (len(x) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    fr = x[idx]
    return 20 * np.log10(np.sqrt(np.mean(fr ** 2, axis=1)) + 1e-9)


def spec_feats(x, sr):
    """谱质心/倾斜/平坦度/高频比（语音帧上取中位）。"""
    import librosa
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    power = S ** 2
    tot = power.sum(0) + 1e-12
    # 只在能量前 40% 的帧上算（语音帧）
    thr = np.quantile(tot, 0.60)
    m = tot >= thr
    if m.sum() < 5:
        m = np.ones_like(tot, dtype=bool)
    P = power[:, m]
    T = tot[m]
    cen = (freqs[:, None] * P).sum(0) / T
    # 谱倾斜：log 功率对 log 频率的斜率（dB/octave）
    lf = np.log2(np.maximum(freqs[1:], 20.0))
    lp = 10 * np.log10(P[1:] + 1e-12)
    A = np.vstack([lf, np.ones_like(lf)])
    coef, *_ = np.linalg.lstsq(A.T, lp, rcond=None)
    slope = coef[0]
    # 平坦度（几何均值/算术均值）
    flat = np.exp(np.mean(np.log(P + 1e-12), 0)) / (np.mean(P, 0) + 1e-12)
    # >4k 能量比
    hi = freqs >= 4000
    hf = P[hi].sum(0) / (P.sum(0) + 1e-12)
    return dict(cent=float(np.median(cen)), tilt=float(np.median(slope)),
                flat=float(np.median(flat)), hf=float(np.median(hf)))


def slopes(f, db, sr, win=0.25, hop=0.06):
    """head/tail 半音斜率（st/s），复刻 mt_metric_audit 口径。"""
    st = 12 * np.log2(np.maximum(f, 1e-3) / 100.0)
    v = f > 0
    if v.sum() < 20:
        return None, None
    t = np.arange(len(f)) * 0.01
    tv, sv = t[v], st[v]
    w, h = win, hop
    pts = []
    t0 = tv[0]
    while t0 + w <= tv[-1]:
        m = (tv >= t0) & (tv < t0 + w)
        if m.sum() >= 8:
            pts.append((t0 + w / 2, np.median(sv[m])))
        t0 += h
    if len(pts) < 4:
        return None, None
    pts = np.array(pts)
    k = max(1, len(pts) // 5)
    hx, hy = pts[:k, 0], pts[:k, 1]
    tx, ty = pts[-k:, 0], pts[-k:, 1]
    return (float(np.polyfit(hx, hy, 1)[0]) if len(hx) > 1 else None,
            float(np.polyfit(tx, ty, 1)[0]) if len(tx) > 1 else None)


def rev_rate(f, win=0.25, hop=0.06):
    st = 12 * np.log2(np.maximum(f, 1e-3) / 100.0)
    v = f > 0
    if v.sum() < 20:
        return None
    t = np.arange(len(f)) * 0.01
    tv, sv = t[v], st[v]
    pts = []
    t0 = tv[0]
    while t0 + win <= tv[-1]:
        m = (tv >= t0) & (tv < t0 + win)
        if m.sum() >= 8:
            pts.append(np.median(sv[m]))
        t0 += hop
    if len(pts) < 3:
        return None
    d = np.diff(pts)
    s = np.sign(d[d != 0])
    if len(s) < 2:
        return None
    return float(np.sum(s[1:] != s[:-1]) / (len(pts) * hop))


def energy_span(db, f, sr):
    """语音帧口径：db > p90-25 剔静音 → 等分 21 段取 p90 → 极差。"""
    p90 = np.percentile(db, 90)
    voiced = db > (p90 - 25)
    if voiced.sum() < 42:
        return None
    seg = np.array_split(db[voiced], 21)
    prof = [np.percentile(s, 90) if len(s) else -99 for s in seg]
    return float(max(prof) - min(prof))


def measure(p):
    x, sr = read(p)
    f = pitch(x, sr)
    fv = robust_f0(f)
    db = frame_db(x, sr)
    sp = spec_feats(x, sr)
    hs, ts = slopes(f, db, sr)
    # parselmouth 微扰
    import parselmouth
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    try:
        pp = snd.to_point_process_cc()
        jit = float(pp.get_jitter_local())
    except Exception:
        jit = None
    try:
        harm = snd.to_harmonicity_cc()
        hnr = float(np.median(harm.values[harm.values > -100])) if harm else None
    except Exception:
        hnr = None
    # 浊音帧占比 / 八度错率
    vo = float((f > 0).mean()) if len(f) else 0.0
    oct_skip = 1 - len(fv) / max(1, (f > 0).sum())
    crest = float(np.max(np.abs(x)) / (np.sqrt(np.mean(x ** 2)) + 1e-12))
    return dict(
        dur=len(x) / sr,
        sp_sec=float((db > np.percentile(db, 90) - 25).sum() * 0.01),
        f0_med=float(np.median(fv)) if len(fv) else None,
        span_st=float(12 * np.log2(np.percentile(fv, 90) / np.percentile(fv, 10)))
        if len(fv) > 10 else None,
        rev=rev_rate(f), head=hs, tail=ts,
        espan=energy_span(db, f, sr),
        voiced=vo, octskip=oct_skip, hnr=hnr, jitter=jit, crest=crest,
        **sp)


KEYS = [("span_st", "F0 跨度(st)", "mono"),
        ("rev", "方向反转率", "mono"),
        ("head", "句首斜率", "mono"),
        ("tail", "句尾斜率", "mono"),
        ("espan", "能量跨度(dB)", "flatamp"),
        ("hnr", "HNR(dB)", "jitter"),
        ("jitter", "jitter", "jitter"),
        ("crest", "峰值因数(dB)", "clip"),
        ("hf", ">4k 能量比", "lowpass"),
        ("cent", "谱质心(Hz)", "lowpass"),
        ("tilt", "谱倾斜", "lowpass"),
        ("flat", "谱平坦度", "stutter"),
        ("voiced", "浊音帧占比", "hole"),
        ("octskip", "八度错率", "jitter")]


def main():
    rows = {}
    for u in UIDS:
        p = os.path.join(PICK, u + ".wav")
        if os.path.exists(p):
            rows[u + "_good"] = measure(p)
    for u in UIDS:
        for d in DEGS:
            p = os.path.join(DEG, "%s_%s.wav" % (u, d))
            if os.path.exists(p):
                rows["%s_%s" % (u, d)] = measure(p)
    # 正常抖动：同 uid 不同 seed
    jit_rows = {}
    for p in glob.glob(os.path.join(HERE, "_mt_adv_ctl_*", "N*.wav")):
        k = os.path.basename(p)[:-4]
        if k not in [u for u in UIDS]:
            continue
        try:
            jit_rows.setdefault(k, []).append(measure(p))
        except Exception as e:
            print("skip", p, e)
    json.dump(dict(rows=rows, jitter={k: v for k, v in jit_rows.items()}),
              open(os.path.join(HERE, "_drop_audit.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("measured %d files, jitter groups %d" % (len(rows), len(jit_rows)))


if __name__ == "__main__":
    main()
