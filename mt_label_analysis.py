# -*- coding: utf-8 -*-
"""用 60 条人工标注标定择优规则。

输出：
  1. 各指标名次分布（1 = 该句最高）
  2. 单规则命中率
  3. 组合规则网格 + 留一交叉验证（防过拟合）
  4. 最终推荐规则与阈值
"""
import json
import os
import sys
import itertools
import numpy as np

ROOT = "G:/_setup"
LAB = os.path.join(ROOT, "_mt_labels_live.json")
CHS = ["ch1", "ch2", "ch3"]

FEATS = ["cen", "spk", "mos", "f0", "dur", "wpm", "ratio"]


def load():
    lab = json.load(open(LAB, encoding="utf-8"))
    sc = {}
    for ch in CHS:
        for x in json.load(open(os.path.join(ROOT, "_mt_score_%s.json" % ch), encoding="utf-8")):
            sc[x["id"]] = (ch, x)

    rows = []          # (uid, ch, cands[list of dict], pick_seed, words, text)
    skipped = []
    for uid, v in lab.items():
        if v["pick"] == "none":
            skipped.append((uid, "none"))
            continue
        if uid not in sc:
            skipped.append((uid, "no-score"))
            continue
        ch, x = sc[uid]
        cands = [c for c in x["cands"] if not c["bad"]]
        if len(cands) < 2:
            skipped.append((uid, "lt2"))
            continue
        if not any(str(c["seed"]) == str(v["pick"]) for c in cands):
            skipped.append((uid, "pick-not-in-cands"))
            continue
        rows.append(dict(uid=uid, ch=ch, cands=cands, pick=str(v["pick"]),
                         words=len(x["text"].split()), text=x["text"],
                         cur=str(x["pick"])))
    return rows, skipped


def fval(c, f):
    if f == "cen":
        return float(c["centroid"])
    if f == "spk":
        v = c.get("spk")
        return None if v is None or v != v else float(v)
    if f == "mos":
        v = c.get("mos")
        return None if v is None else float(v)
    if f == "f0":
        v = float(c["f0"])
        return None if v <= 1 else v
    if f == "dur":
        return float(c["dur"])
    if f == "wpm":
        return float(c["final_wpm"])
    if f == "ratio":
        return float(c["ratio"])
    raise KeyError(f)


def zmat(cands, feats):
    """按单元内 z 归一化；缺失值填 0（中性）。"""
    n = len(cands)
    M = np.zeros((n, len(feats)), dtype=np.float64)
    for j, f in enumerate(feats):
        vals = [fval(c, f) for c in cands]
        ok = [v for v in vals if v is not None]
        if len(ok) < 2:
            continue
        mu = float(np.mean(ok))
        sd = float(np.std(ok))
        if sd < 1e-9:
            continue
        for i, v in enumerate(vals):
            M[i, j] = 0.0 if v is None else (v - mu) / sd
    return M


def build_matrix(rows):
    """预先把每个单元的 z 矩阵和正确索引算好。"""
    out = []
    for r in rows:
        M = zmat(r["cands"], FEATS)
        seeds = [str(c["seed"]) for c in r["cands"]]
        yi = seeds.index(r["pick"])
        out.append((M, yi, seeds))
    return out


def acc_of(mats, w):
    """给定权重向量 w，返回命中率。"""
    ok = 0
    for M, yi, seeds in mats:
        s = M @ w
        if int(np.argmax(s)) == yi:
            ok += 1
    return ok


def main():
    rows, skipped = load()
    print("可用标注 %d 条；跳过 %d 条 %s" % (len(rows), len(skipped), skipped[:6]))
    from collections import Counter
    print("候选数分布:", dict(sorted(Counter(len(r["cands"]) for r in rows).items())))
    print("章分布:", dict(sorted(Counter(r["ch"] for r in rows).items())))
    w = np.array([r["words"] for r in rows])
    print("词数: 中位 %d  范围 %d-%d  >14 词 %d 条" % (np.median(w), w.min(), w.max(), (w > 14).sum()))
    print()

    # ---------- 1. 各指标名次 ----------
    print("=== 用户所选在该指标上的名次（1 = 该句最高）===")
    print("%-8s %5s %8s %8s %9s %9s" % ("指标", "n", "第1名%", "末名%", "平均名次", "随机期望"))
    for f in FEATS:
        rs = []
        for r in rows:
            vals = [(str(c["seed"]), fval(c, f)) for c in r["cands"]]
            vals = [(s, v) for s, v in vals if v is not None]
            if len(vals) < 2:
                continue
            vals.sort(key=lambda t: -t[1])
            order = [s for s, _ in vals]
            if r["pick"] not in order:
                continue
            rs.append((order.index(r["pick"]) + 1, len(order)))
        if not rs:
            continue
        n1 = sum(1 for a, b in rs if a == 1)
        nl = sum(1 for a, b in rs if a == b)
        print("%-8s %5d %7.0f%% %7.0f%% %9.2f %9.2f"
              % (f, len(rs), 100 * n1 / len(rs), 100 * nl / len(rs),
                 np.mean([a for a, _ in rs]), np.mean([(b + 1) / 2 for _, b in rs])))
    print()

    # ---------- 2. 单规则命中 ----------
    print("=== 单规则命中率 ===")
    for f, sign, name in [("cen", -1, "重心最低"), ("cen", +1, "重心最高"),
                          ("spk", +1, "声纹最高"), ("spk", -1, "声纹最低"),
                          ("mos", +1, "MOS 最高"), ("mos", -1, "MOS 最低"),
                          ("f0", +1, "F0 最高"), ("f0", -1, "F0 最低"),
                          ("dur", +1, "最长"), ("dur", -1, "最短"),
                          ("wpm", +1, "最快"), ("wpm", -1, "最慢"),
                          ("ratio", +1, "ASR 最高")]:
        wv = np.zeros(len(FEATS))
        wv[FEATS.index(f)] = sign
        mats = build_matrix(rows)
        print("  %-10s %3d/%2d = %3.0f%%" % (name, acc_of(mats, wv), len(rows),
                                             100 * acc_of(mats, wv) / len(rows)))
    # 当前打分器
    ok = sum(1 for r in rows if r["cur"] == r["pick"])
    print("  %-10s %3d/%2d = %3.0f%%" % ("当前打分器", ok, len(rows), 100 * ok / len(rows)))
    print()

    # ---------- 3. 组合网格 + LOO ----------
    mats = build_matrix(rows)
    grid = []
    for combo in itertools.product([-1, 0, 1], repeat=len(FEATS)):
        wv = np.array(combo, dtype=np.float64)
        if not np.any(wv):
            continue
        grid.append((acc_of(mats, wv), wv))
    grid.sort(key=lambda t: -t[0])
    print("=== 全样本最优组合 Top 8 ===")
    for a, wv in grid[:8]:
        terms = " ".join("%s%+d" % (FEATS[i], int(wv[i])) for i in range(len(FEATS)) if wv[i])
        print("  %3d/%2d = %3.0f%%   %s" % (a, len(rows), 100 * a / len(rows), terms))
    print()

    print("=== 留一交叉验证（每折在 57 条上重选组合）===")
    ok = 0
    picks = []
    for i in range(len(rows)):
        tr = [m for j, m in enumerate(mats) if j != i]
        best = None
        for a, wv in grid:
            aa = acc_of(tr, wv)
            if best is None or aa > best[0]:
                best = (aa, wv)
        M, yi, _ = mats[i]
        pred = int(np.argmax(M @ best[1]))
        ok += int(pred == yi)
        picks.append((rows[i]["uid"], pred == yi))
    print("  LOO 命中 %d/%d = %.0f%%" % (ok, len(rows), 100 * ok / len(rows)))
    # 与"重心最低"基线比较
    wv = np.zeros(len(FEATS)); wv[FEATS.index("cen")] = -1
    print("  同期「重心最低」全样本命中 %d/%d = %.0f%%"
          % (acc_of(mats, wv), len(rows), 100 * acc_of(mats, wv) / len(rows)))
    print()

    # ---------- 4. 分层 ----------
    print("=== 分层：重心最低 vs LOO 最优组合 ===")
    wv_c = np.zeros(len(FEATS)); wv_c[FEATS.index("cen")] = -1
    for lo, hi, nm in [(0, 7, "短 <8"), (8, 14, "中 8-14"), (15, 99, "长 >15")]:
        idx = [i for i, r in enumerate(rows) if lo <= r["words"] <= hi]
        if not idx:
            continue
        a = sum(1 for i in idx if int(np.argmax(mats[i][0] @ wv_c)) == mats[i][1])
        print("  %-9s n=%2d  重心最低 %2d = %3.0f%%" % (nm, len(idx), a, 100 * a / len(idx)))
    print()

    # ---------- 5. 重心差的分布 ----------
    print("=== 选中项与「最暗候选」的重心差 ===")
    d = []
    for r in rows:
        lo = min(r["cands"], key=lambda z: z["centroid"])
        pick = [c for c in r["cands"] if str(c["seed"]) == r["pick"]][0]
        d.append((pick["centroid"] - lo["centroid"], r["uid"], r["words"]))
    d.sort(key=lambda t: -t[0])
    arr = np.array([x[0] for x in d])
    print("  差 中位 %.0f  p90 %.0f  最大 %.0f | 恰好选最暗 %d 条"
          % (np.median(arr), np.percentile(arr, 90), arr.max(), (arr < 1).sum()))
    print("  选了更亮且差 >300Hz 的：%d 条" % (arr > 300).sum())
    for x in d[:6]:
        print("    %s 差 %+.0f Hz  %d 词" % (x[1], x[0], x[2]))
    print()

    # ---------- 6. 重心绝对值分布 ----------
    print("=== 标注单元的重心绝对值 ===")
    ch_c = []
    lo_c = []
    for r in rows:
        pick = [c for c in r["cands"] if str(c["seed"]) == r["pick"]][0]
        ch_c.append(pick["centroid"])
        lo_c.append(min(c["centroid"] for c in r["cands"]))
    print("  被选中的重心: 中位 %.0f  p10 %.0f  p90 %.0f  最低 %.0f  最高 %.0f"
          % (np.median(ch_c), np.percentile(ch_c, 10), np.percentile(ch_c, 90),
             min(ch_c), max(ch_c)))
    print("  每句最暗候选: 中位 %.0f  p10 %.0f  p90 %.0f"
          % (np.median(lo_c), np.percentile(lo_c, 10), np.percentile(lo_c, 90)))


if __name__ == "__main__":
    main()
