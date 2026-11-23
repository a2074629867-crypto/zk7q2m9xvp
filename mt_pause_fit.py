# -*- coding: utf-8 -*-
"""mt_pause_fit.py —— 从马修母带拟合「逐处停顿时长」，而不是按标点给固定值。

问题（用户 2026-10-29 指出）：`Yes. No. Well, it was in somebody's house.`
三个边界在真人嘴里长短不同，但现有系统按标点档位给固定值。

做法：
  1) 读 v6 切片标签（455 条，含文本 + 采样点边界）
  2) 每两片之间的间隙 = 一处停顿；用「前片文本 / 后片文本」构造上下文特征
  3) OLS 拟合 log(gap) ~ 特征，输出系数 + 残差 sd
  4) 对照组：只用标点类型的常数模型（现有生产逻辑），比 MAE / 预测跨度

特征全部只依赖文本，所以能直接迁移到我们自己的台词。

用法:
  python mt_pause_fit.py            # 拟合 + 报告
  python mt_pause_fit.py --show 20  # 额外打印 20 个样本对照
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

LAB = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")
SR = 32000
OUT = Path("G:/_setup/pause_model.json")

PUNCT_MAP = {",": "comma", ".": "period", "?": "question", "!": "excl",
             ";": "semicolon", ":": "colon", "…": "ellipsis"}
FUNC = {"the", "a", "an", "and", "but", "or", "so", "then", "of", "to", "in",
        "on", "at", "for", "with", "he", "she", "it", "i", "you", "we", "they",
        "his", "her", "my", "your", "that", "this", "was", "is", "were", "are",
        "had", "have", "has", "don't", "didn't", "can't", "couldn't", "not"}


def load_rows():
    rows = []
    for line in LAB.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        m = re.search(r"_(\d+)_(\d+)\.wav$", p[0])
        if not m:
            continue
        a, b = int(m.group(1)) / SR, int(m.group(2)) / SR
        t = p[3].strip()
        if not t:
            continue
        rows.append((a, b, t))
    rows.sort()
    return rows


def tail_punct(t):
    s = t.rstrip()
    while s and s[-1] in "\"')":
        s = s[:-1]
    return s[-1] if s else ""


def featurize(prev_t, next_t, punct):
    """只依赖文本的特征。返回 (名字列表, 向量)。"""
    pw = prev_t.split()
    nw = next_t.split()
    lp = np.log1p(len(pw))
    ln = np.log1p(len(nw))
    nxt0 = re.sub(r"[^a-z']", "", nw[0].lower()) if nw else ""
    f = {
        "const": 1.0,
        "lp": lp,                       # 前片词数（说完多长一段）
        "ln": ln,                       # 后片词数（要准备多长的下一段）
        "prev_short": 1.0 if len(pw) <= 3 else 0.0,
        "prev_tiny": 1.0 if len(pw) <= 1 else 0.0,
        "next_func": 1.0 if nxt0 in FUNC else 0.0,
        "is_period": 1.0 if punct == "." else 0.0,
        "is_comma": 1.0 if punct == "," else 0.0,
        "is_question": 1.0 if punct == "?" else 0.0,
        "lp_x_period": lp * (1.0 if punct == "." else 0.0),
    }
    return list(f.keys()), np.array([f[k] for k in f])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    rows = load_rows()
    print("切片 %d 条，覆盖 %.1f~%.1fs" % (len(rows), rows[0][0], rows[-1][1]))

    X, Y, meta = [], [], []
    for k in range(len(rows) - 1):
        e, s = rows[k][1], rows[k + 1][0]
        gap = s - e
        if gap <= 0.02:
            continue
        p = tail_punct(rows[k][2])
        if p not in PUNCT_MAP:
            continue
        if p in (";", ":", "…"):          # 样本太少，不参与拟合
            continue
        names, v = featurize(rows[k][2], rows[k + 1][2], p)
        X.append(v)
        Y.append(np.log(gap))
        meta.append(dict(gap=gap, punct=p, prev=rows[k][2], nxt=rows[k + 1][2]))

    X = np.vstack(X)
    Y = np.array(Y)
    names = names
    n, p = X.shape
    print("参与拟合 %d 处（标点类 %d）" % (n, p))

    # ---- 模型 ----
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    pred = X @ beta
    res = Y - pred
    sd = float(res.std(ddof=p))
    ss_tot = ((Y - Y.mean()) ** 2).sum()
    r2 = 1 - (res ** 2).sum() / ss_tot

    print()
    print("=== 模型 log(gap) ~ 上下文 ===")
    print("%-14s %8s" % ("特征", "系数"))
    for nm, b in zip(names, beta):
        print("%-14s %+8.3f" % (nm, b))
    print("R² = %.3f   残差 sd = %.3f (log)   样本 %d" % (r2, sd, n))

    # ---- 对照组：只用标点的常数模型（≈现有生产逻辑）----
    pmean = {k: float(Y[[i for i, m in enumerate(meta) if m["punct"] == k]].mean())
             for k in set(m["punct"] for m in meta)}
    pred0 = np.array([pmean[m["punct"]] for m in meta])
    res0 = Y - pred0
    r2_0 = 1 - (res0 ** 2).sum() / ss_tot
    print()
    print("=== 对照：只按标点给常数 ===")
    for k, v in sorted(pmean.items(), key=lambda t: -t[1]):
        print("  %-9s n=%3d  常数 %.2fs" % (k, sum(1 for m in meta if m["punct"] == k),
                                          float(np.exp(v))))
    print("  R² = %.3f   残差 sd = %.3f (log)" % (r2_0, float(res0.std(ddof=1))))

    # ---- 秒域误差 + 预测跨度（用户关心的是「有没有长有短」）----
    g = np.array([m["gap"] for m in meta])
    e1 = np.abs(np.exp(pred) - g)
    e0 = np.abs(np.exp(pred0) - g)
    print()
    print("=== 秒域 ===")
    print("常数模型 MAE %.3fs   上下文模型 MAE %.3fs   (改善 %.1f%%)"
          % (e0.mean(), e1.mean(), 100 * (1 - e1.mean() / e0.mean())))
    print("实际 gap 跨度 %.2f~%.2fs" % (g.min(), g.max()))
    print("常数模型预测跨度 %.2f~%.2fs（同一标点只给一个值）"
          % (np.exp(pred0).min(), np.exp(pred0).max()))
    print("上下文模型预测跨度 %.2f~%.2fs" % (np.exp(pred).min(), np.exp(pred).max()))

    # ---- 残差分布（给采样用，保证同一预测值也能有长短）----
    qs = np.percentile(res, [5, 25, 50, 75, 95])
    print()
    print("残差分位 (log): p5 %+.3f  p25 %+.3f  中位 %+.3f  p75 %+.3f  p95 %+.3f"
          % tuple(qs))

    # ---- 短单元序列：直接回答用户举的那句 ----
    print()
    print("=== 短单元（前片 ≤3 词且以句号结尾）实际停顿 ===")
    short = [(m["gap"], m["prev"], m["nxt"]) for m in meta
             if m["punct"] == "." and len(m["prev"].split()) <= 3]
    print("n=%d  中位 %.2fs  p10 %.2fs  p90 %.2fs  跨度 %.2f~%.2fs"
          % (len(short), np.median([s[0] for s in short]),
             np.percentile([s[0] for s in short], 10),
             np.percentile([s[0] for s in short], 90),
             min(s[0] for s in short), max(s[0] for s in short)))
    for gap, pv, nx in short[:12]:
        print("  %.2fs | %-26s → %s" % (gap, pv[:26], nx[:34]))

    print()
    print("=== 逗号：前片词数 vs 实际停顿 ===")
    for lo, hi in ((1, 2), (3, 4), (5, 7), (8, 30)):
        v = [m["gap"] for m in meta if m["punct"] == ","
             and lo <= len(m["prev"].split()) <= hi]
        if len(v) >= 3:
            print("  %2d-%2d 词  n=%3d  中位 %.2fs  IQR %.2f~%.2fs"
                  % (lo, hi, len(v), np.median(v),
                     np.percentile(v, 25), np.percentile(v, 75)))

    if a.show:
        print()
        print("=== 样本对照（实测 / 常数 / 上下文）===")
        idx = np.argsort(-g)[:a.show]
        for i in idx:
            print("  %5.2fs  常数%5.2f  模型%5.2f | %-24s → %s"
                  % (g[i], np.exp(pred0[i]), np.exp(pred[i]),
                     meta[i]["prev"][:24], meta[i]["nxt"][:30]))

    json.dump(dict(names=names, beta=[float(b) for b in beta], r2=float(r2),
                   resid_sd=sd, resid_q=[float(q) for q in qs],
                   n=int(n),
                   punct_const={k: float(np.exp(v)) for k, v in pmean.items()},
                   meta=dict(mae_const=float(e0.mean()), mae_model=float(e1.mean()))),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print()
    print("已写", a.out)


if __name__ == "__main__":
    main()
