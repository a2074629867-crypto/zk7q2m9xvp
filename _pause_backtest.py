# -*- coding: utf-8 -*-
"""_pause_backtest.py —— 用「规则预测值」回测马修真人 641 个间隙，给诚实误差。

规则：逗号 1.17s / 句号 1.76s / 段落 2.50s / 句中 0.20s（只对超长句）
指标：MAE、RMSE、落在实测 p25-p75 区间的比例、方向偏差（预测偏长/偏短）
"""
import bisect
import json
import re
from collections import defaultdict

import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
RULES = "G:/_setup/mc_pause_rules.json"
SR = 32000

rules = json.load(open(RULES, encoding="utf-8"))


def med(k, fb):
    p = rules.get("punct", {}).get(k)
    return p["stats"]["median"] if p and p.get("stats") else fb


C_COMMA = med("comma", 1.17)
C_PERIOD = med("period", 1.76)
C_PARA = 1.48   # 无标点长停用「长停中位」兜底，不能按段落 2.5s
C_BREATH = 0.20


def vad_segments():
    x, sr = sf.read(MASTER, dtype="float64", always_2d=True)
    x = x.mean(1)
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < 8:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < 12:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return segs


segs = vad_segments()
d = json.load(open(WORDS, encoding="utf-8"))
words = []
for s in d["slices"]:
    for t0, t1, w in s.get("words", []):
        words.append((float(t0), float(t1), w))
words.sort(key=lambda t: t[0])
t0s = [a for a, b, _ in words]

P = re.compile(r"([,\.\?;:!]+)\s*$")
gaps = []
for k in range(1, len(segs)):
    g0, g1 = segs[k - 1][1], segs[k][0]
    if g1 - g0 < 0.06:
        continue
    pi = bisect.bisect_right(t0s, g0) - 1
    ni = bisect.bisect_left(t0s, g1)
    if pi < 0 or ni >= len(words) or ni <= pi:
        continue
    m = P.search(words[pi][2])
    gaps.append(dict(dur=g1 - g0, pi=pi, ni=ni, mark=m.group(1)[0] if m else None))


def backtest(name, sel, pred):
    a = np.array([g["dur"] for g in sel])
    p = np.full(len(a), pred)
    mae = np.abs(a - p).mean()
    rmse = np.sqrt(((a - p) ** 2).mean())
    p25, p75 = np.percentile(a, 25), np.percentile(a, 75)
    inside = ((a >= p25) & (a <= p75)).mean()
    bias = p.mean() - a.mean()
    print("  %-10s n=%3d  实测中位%.2f  预测%.2f  MAE %.3fs  RMSE %.3f  落在p25-p75 %.0f%%  偏差%+.3f"
          % (name, len(a), np.median(a), pred, mae, rmse, 100 * inside, bias))
    return dict(n=len(a), real_median=round(float(np.median(a)), 3), pred=pred,
                mae=round(float(mae), 3), rmse=round(float(rmse), 3),
                in_iqr=round(float(inside), 3), bias=round(float(bias), 3))


print("=" * 78)
print("回测：用固定规则预测马修每个间隙")
out = {}
out["comma"] = backtest("逗号", [g for g in gaps if g["mark"] == ","], C_COMMA)
out["period"] = backtest("句号", [g for g in gaps if g["mark"] == "."], C_PERIOD)
out["short"] = backtest("句中短停", [g for g in gaps if not g["mark"] and g["dur"] < 0.6], C_BREATH)
out["long_nomark"] = backtest("无标点长停", [g for g in gaps if not g["mark"] and g["dur"] >= 0.6], C_PARA)

# 整体：按标点给预测值
preds, reals = [], []
for g in gaps:
    if g["mark"] == ",":
        preds.append(C_COMMA)
    elif g["mark"] in (".", "?", "!"):
        preds.append(C_PERIOD)
    elif not g["mark"] and g["dur"] < 0.6:
        preds.append(C_BREATH)
    else:
        preds.append(C_PARA)
    reals.append(g["dur"])
a = np.array(reals)
p = np.array(preds)
print("\n  全量 641 个：MAE %.3fs  中位误差 %.3fs  相关系数 %.3f"
      % (np.abs(a - p).mean(), np.median(np.abs(a - p)), np.corrcoef(a, p)[0, 1]))
out["all"] = dict(mae=round(float(np.abs(a - p).mean()), 3),
                  med_ae=round(float(np.median(np.abs(a - p))), 3),
                  corr=round(float(np.corrcoef(a, p)[0, 1]), 3))

# 总时长守恒检验
print("  真人总静音 %.1fs | 规则预测总静音 %.1fs | 差 %.1f%%"
      % (a.sum(), p.sum(), 100 * (p.sum() - a.sum()) / a.sum()))

json.dump(out, open("G:/_setup/mc_pause_backtest.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n写出 G:/_setup/mc_pause_backtest.json")
