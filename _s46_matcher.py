# -*- coding: utf-8 -*-
"""_s46_matcher.py —— 以 s46 为参照找「语调像 s46、但 can't 的 /t/ 清楚」的 take

用户口径（2026-11-25 08:4x 明确纠正）：
  「s46 的问题根本不是语调，它这个就也很好了……我是觉得 s46 是最合适罢了。
    我之前跟你说过，他的问题是他把 can't 读成了 cam I」

⇒ 判据必须改：
  1) **语调不提分**：s46 的语调就是目标，不是「不够好」。之前用 rng 越大越好去排，
     等于让模型越夸张越好，方向错了。
  2) **唯一的硬指标是 /t/ 有没有释放**，而且必须**裁掉词尾静音后再量**（否则量到静音，
     s46 会被量成 0.170，结论反了 —— 这个坑已经踩过一次）。

本脚本产出两张表：
  A. 每个 take 对 s46 的**语调距离**（逐词 F0 轮廓，半音刻度，重采样到 12 点后比）
  B. 每个 take 的**词尾释放**（裁静音后 hf_tail / hf_jump / 闭合深度）
两者交叉：距离小 + 释放够 ⇒ s46 的语调 + 能听见 t。
"""
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")

STEP = 0.01
NPT = 12
REF = "s46"


def paths(rid="c3_0853", pools=("_seedpick2", "_pool2", "_seedpick")):
    d = {"now": "G:/_setup/_audio_ch123/out/%s.wav" % rid}
    for pool in pools:     # 后面的覆盖前面的
        for p in glob.glob("G:/_setup/%s/%s/s*.wav" % (pool, rid)):
            d[os.path.basename(p)[:-4]] = p
    return d


def f0_full(p):
    f = parselmouth.Sound(p).to_pitch(STEP, 75, 600).selected_array["frequency"]
    return np.where(f > 0, f, np.nan)


def resample(v, n=NPT):
    """把词内 F0（半音）重采样到 n 点；NaN 交给 np.interp 前先线性填补。"""
    v = np.asarray(v, dtype="float64")
    if len(v) < 2:
        return None
    x = np.arange(len(v))
    ok = ~np.isnan(v)
    if ok.sum() < 3:
        return None
    vv = np.interp(x, x[ok], v[ok])
    xi = np.linspace(0, len(v) - 1, n)
    return np.interp(xi, x, vv)


def contour(p, spans, med_ref=None):
    f = f0_full(p)
    med = med_ref if med_ref else float(np.nanmedian(f))
    out = []
    for w, a, b in spans:
        i0, i1 = int(a / STEP), max(int(b / STEP), int(a / STEP) + 1)
        seg = f[i0:i1]
        if np.isnan(seg).all():
            out.append(None)
            continue
        out.append(resample(12.0 * np.log2(seg / med)))
    return out, med


def trim_tail(y, sr, a, b, rel_db=-26.0, guard_ms=20.0):
    """把词尾静音切掉：从 b 往前找最后一个「有声帧」，返回真实结束点。
    rel_db 相对词内最大帧能量，低于它就算静音。"""
    n = int(0.01 * sr)
    i0, i1 = int(a * sr), int(b * sr)
    seg = y[i0:i1]
    c = len(seg) // max(n, 1)
    if c < 3:
        return b
    db = np.array([10 * np.log10((seg[i * n:(i + 1) * n] ** 2).sum() + 1e-12) for i in range(c)])
    thr = db.max() + rel_db
    voice = np.where(db > thr)[0]
    if not len(voice):
        return b
    last = voice[-1]
    end = a + (last + 1) * 0.01
    return min(b, max(end, a + 0.03))


def audible_gap(p, a, b, rel=30.0):
    """听得见的间隔：对齐边界含元音拖尾，会把间隔虚报 ~250ms。

    以该区间 85 分位能量为语音电平，低于 (电平-30dB) 算静音，取最长连续静音段。
    用户口径「I 与 I 之间最多 0.2 秒」应该用这个量，不是对齐边界。
    """
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    n = int(0.01 * sr)
    seg = y[int(a * sr):int(b * sr)]
    c = len(seg) // n
    if c < 4:
        return None
    db = np.array([20 * np.log10(np.sqrt((seg[i * n:(i + 1) * n] ** 2).mean()) + 1e-12) for i in range(c)])
    thr = np.percentile(db, 85) - rel
    low, best, s0 = db < thr, 0, None
    for i, v in enumerate(low):
        if v and s0 is None:
            s0 = i
        if (not v or i == c - 1) and s0 is not None:
            e = i if not v else i + 1
            best = max(best, e - s0)
            s0 = None
    return best * 10


def burst_trim(p, a, b, tail_ms=40.0):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    b2 = trim_tail(y, sr, a, b)
    n = max(16, int(0.01 * sr))
    i0, i1 = int(a * sr), int(b2 * sr)
    seg = y[i0:i1]
    c = len(seg) // n
    if c < 3:
        return None
    w = np.hanning(n)
    fr, hf, cen = np.fft.rfftfreq(n, 1.0 / sr), [], []
    for i in range(c):
        sp = np.abs(np.fft.rfft(seg[i * n:(i + 1) * n] * w))
        e = float((sp ** 2).sum()) + 1e-12
        hf.append(float((sp[fr >= 3500] ** 2).sum()) / e)
        cen.append(float((sp * fr).sum() / (sp.sum() + 1e-12)))
    nt = max(2, int(tail_ms / 10))
    body = slice(2, max(3, len(hf) - nt))
    ht, hb = float(np.mean(hf[-nt:])), float(np.mean(hf[body]))
    ct, cb = float(np.mean(cen[-nt:])), float(np.mean(cen[body]))
    db = [10 * np.log10((seg[i * n:(i + 1) * n] ** 2).sum() + 1e-12) for i in range(c)]
    return dict(dur=round((b2 - a) * 1000), cut_ms=round((b - b2) * 1000),
                hf_tail=round(ht, 3), hf_body=round(hb, 3),
                hf_jump=round(ht / max(hb, 1e-6), 2),
                cen_tail=round(ct), cen_body=round(cb),
                cen_jump=round(ct / max(cb, 1e-6), 2),
                closure_db=round(max(db) - min(db[-nt:]), 1))


def main():
    rank = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_pool_rank.json"
    pools = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("_seedpick2", "_pool2", "_seedpick")
    outp = sys.argv[3] if len(sys.argv) > 3 else "G:/_setup/_s46_match.json"
    d = json.load(open(rank, encoding="utf-8"))
    rows = {r["tag"]: r for r in d["rows"]}
    P = paths(pools=pools)
    ref = rows[REF]
    refc, refmed = contour(P[REF], [(s[0], s[1], s[2]) for s in ref["spans"]])
    out = {}
    for tag, r in rows.items():
        p = P.get(tag)
        if not p or not os.path.exists(p):
            continue
        spans = [(s[0], s[1], s[2]) for s in r["spans"]]
        cur, med = contour(p, spans)
        dd = []
        for i, (a, b) in enumerate(zip(refc, cur)):
            if a is None or b is None:
                continue
            dd.append(float(np.mean(np.abs(a - b))))
        # 目标词 cant 的释放
        cant = [s for s in spans if s[0].startswith("cant")]
        bs = burst_trim(p, cant[0][1], cant[0][2]) if cant else None
        # 「I – I」两个 I 之间的间隔（用户 2026-11-25 08:44：差 0 点最好，最多 0.2s）
        igap = None
        if len(spans) >= 2 and spans[0][0].startswith("i") and spans[1][0].startswith("i"):
            igap = round((spans[1][1] - spans[0][2]) * 1000)
            igap_aud = audible_gap(p, spans[0][2], spans[1][1])
        out[tag] = dict(contour_dist=round(float(np.mean(dd)), 2) if dd else None,
                        nword=len(dd), f0_med=int(med),
                        dur=round(len(sf.read(p, dtype="float32")[0]) /
                                  sf.read(p, dtype="float32")[1], 2),
                        i_gap_ms=igap, i_gap_aud_ms=igap_aud, burst=bs)
    json.dump(out, open(outp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("%-4s %8s %6s %7s %7s %7s %6s %7s %s" % (
        "tag", "语调距离", "n词", "hfTail", "hfJump", "cenJump", "闭合dB", "I-I间隔", "裁掉ms"))
    for tag, v in sorted(out.items(), key=lambda kv: (kv[1]["contour_dist"] or 99)):
        b = v["burst"] or {}
        mark = " ← 参照" if tag == REF else ""
        print("%-4s %8.2f %6d %7.3f %7.2f %7.2f %6.1f %6sms %s%s" % (
            tag, v["contour_dist"] or -1, v["nword"], b.get("hf_tail", -1),
            b.get("hf_jump", -1), b.get("cen_jump", -1), b.get("closure_db", -1),
            v["i_gap_ms"], b.get("cut_ms", "-"), mark))


if __name__ == "__main__":
    sys.exit(main())
