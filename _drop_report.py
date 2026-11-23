# -*- coding: utf-8 -*-
"""_drop_report.py —— 把 _drop_audit.json 算成「弃用指标能不能捞回来」的裁决表。

两个量：
  AUC    好(5) vs 该类退化(5)，Mann-Whitney；0.5=无响应
  SNR    对口劣化 |中位差| ÷ 同 uid 跨 seed 抖动的 pooled SD
          ≥2 可用；1~2 只能组级；<1 无关
"""
import json
import os
import statistics as st

HERE = "G:/_setup"
D = json.load(open(os.path.join(HERE, "_drop_audit.json"), encoding="utf-8"))
ROWS, JIT = D["rows"], D["jitter"]
UIDS = ["N0194", "N0239", "N0254", "N0552", "N0755"]
DEGS = ["chop", "clip", "flatamp", "hole", "jitter", "lowpass", "mono", "stutter"]
KEYS = [
    ("span_st", "F0 跨度 (st)", "mono", "-"),
    ("rev", "方向反转率", "mono", "-"),
    ("head", "句首斜率 (st/s)", "mono", "="),
    ("tail", "句尾斜率 (st/s)", "mono", "="),
    ("espan", "能量跨度 (dB)", "flatamp", "="),
    ("hnr", "HNR (dB)", "jitter", "-"),
    ("jitter", "jitter local", "jitter", "-"),
    ("crest", "峰值因数 (dB)", "clip", "-"),
    ("hf", ">4k 能量比", "lowpass", "-"),
    ("cent", "谱质心 (Hz)", "lowpass", "-"),
    ("tilt", "谱倾斜 (dB/oct)", "lowpass", "="),
    ("flat", "谱平坦度", "stutter", "-"),
    ("voiced", "浊音帧占比", "hole", "-"),
    ("octskip", "八度错率", "jitter", "-"),
]


def vals(sel):
    out = []
    for k, r in ROWS.items():
        if sel(k) and r.get(KEYS[0][0]) is not None:
            pass
    return out


def col(k, pred):
    v = [r.get(k) for kk, r in ROWS.items() if pred(kk) and r.get(k) is not None]
    return v


def auc(good, bad, direction):
    """direction '-' 表示缺陷使值变小。返回按该方向的 AUC。"""
    if not good or not bad:
        return None
    n = 0
    s = 0
    for g in good:
        for b in bad:
            n += 1
            if direction == "-":
                s += 1.0 if g > b else (0.5 if g == b else 0.0)
            else:
                s += 1.0 if g < b else (0.5 if g == b else 0.0)
    return s / n


def noise_sd(k):
    """同 uid 跨 seed 的 pooled within-uid SD。"""
    ss, ws = 0.0, 0
    for u, arr in JIT.items():
        v = [r.get(k) for r in arr if r.get(k) is not None]
        if len(v) < 2:
            continue
        ss += (len(v) - 1) * st.variance(v)
        ws += len(v) - 1
    return (ss / ws) ** 0.5 if ws > 0 else None


out = []
for k, name, deg, direction in KEYS:
    good = col(k, lambda kk: kk.endswith("_good"))
    bad = col(k, lambda kk, d=deg: kk.endswith("_" + d))
    a = auc(good, bad, direction)
    sd = noise_sd(k)
    mg = st.median(good) if good else None
    mb = st.median(bad) if bad else None
    snr = (abs(mg - mb) / sd) if (sd and mg is not None and mb is not None) else None
    out.append(dict(key=k, name=name, deg=deg, n_good=len(good), n_bad=len(bad),
                    good=round(mg, 3) if mg is not None else None,
                    bad=round(mb, 3) if mb is not None else None,
                    auc=round(a, 3) if a is not None else None,
                    sd=round(sd, 3) if sd else None,
                    snr=round(snr, 2) if snr else None))

json.dump(out, open(os.path.join(HERE, "_drop_report.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)

hdr = "| 指标 | 对口退化 | 好 p50 | 坏 p50 | AUC | 抖动 SD | SNR | 裁决 |"
print(hdr)
print("|---|---|---|---|---|---|---|---|")
for r in out:
    if r["auc"] is None:
        v = "无数据"
    elif r["snr"] is None:
        v = "无抖动基准"
    elif r["snr"] >= 2 and r["auc"] >= 0.9:
        v = "**可用（单条）**"
    elif r["snr"] >= 1 and r["auc"] >= 0.8:
        v = "组级可用"
    elif r["auc"] < 0.7:
        v = "无响应"
    else:
        v = "边缘"
    print("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
        r["name"], r["deg"], r["good"], r["bad"], r["auc"], r["sd"], r["snr"], v))
