# -*- coding: utf-8 -*-
"""
_cells_dtw.py —— 用「逐词 F0 序列」而不是 4 个整句标量，检验 cell 分类是否真的有用。

上一版用 span/peak_max/dur/wps 四个标量做最近邻，结果 50%（等于随机）。
原因很可能是：用户说的「同结构同重点 ⇒ 韵律相似」，指的是**词与词之间的走向**，
而 4 个整句标量把走向全扔了。所以这里换成逐词 Δmed 序列 + DTW。

检验：
  同 cell 且同长度档 的随机词对  vs  跨 cell 但同长度档 的随机词对
  比较 DTW 距离分布。同 cell 明显更小 ⇒ 分类有用；差不多 ⇒ 无用。
"""
import json, random, itertools, statistics as st
import numpy as np

random.seed(7)
np.random.seed(7)


def dtw(a, b):
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return None
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            c = abs(ai - b[j - 1])
            D[i, j] = c + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)      # 归一化，避免长句天然更大


def seq_of(r):
    s = [p["d_med"] for p in r["pairs"] if p["d_med"] is not None]
    if len(s) < 4:
        return None
    s = np.array(s, float)
    return (s - s.mean()) / (s.std() + 1e-9)   # 只比形状，不比电平


def main():
    rows = json.load(open("_cells.json", encoding="utf-8"))["rows"]
    P = json.load(open("_prosody5_all.json", encoding="utf-8"))
    seqs = {}
    for r in rows:
        q = seq_of(P[f'{r["id"]}|new'])
        if q is not None:
            seqs[r["id"]] = q
    rows = [r for r in rows if r["id"] in seqs]
    print(f"可用句子 {len(rows)}（序列 ≥4 个词对）")

    by = {}
    for r in rows:
        by.setdefault((r["cell"], r["len"]), []).append(r["id"])
    ids = [r["id"] for r in rows]
    cell = {r["id"]: r["cell"] for r in rows}
    lb = {r["id"]: r["len"] for r in rows}

    def sample_pairs(n, same):
        out = []
        guard = 0
        while len(out) < n and guard < n * 200:
            guard += 1
            a, b = random.sample(ids, 2)
            if lb[a] != lb[b]:
                continue
            if same and cell[a] != cell[b]:
                continue
            if (not same) and cell[a] == cell[b]:
                continue
            d = dtw(seqs[a], seqs[b])
            if d is not None:
                out.append(d)
        return out

    S = sample_pairs(2500, True)
    X = sample_pairs(2500, False)
    print(f"同 cell（同长度）n={len(S)}  DTW 中位={np.median(S):.3f} 均值={np.mean(S):.3f}")
    print(f"跨 cell（同长度）n={len(X)}  DTW 中位={np.median(X):.3f} 均值={np.mean(X):.3f}")
    # 方向：同 cell 应更小
    allv = np.array(S + X); lab = np.array([1] * len(S) + [0] * len(X))
    wins = 0
    for _ in range(2000):
        i, j = np.random.randint(len(S)), np.random.randint(len(X))
        wins += S[i] < X[j]
    print(f"P(同cell 的 DTW < 跨cell) = {wins/2000:.3f}   （0.5 = 分类无用）")
    diff = (np.median(X) - np.median(S)) / np.median(X) * 100
    print(f"中位差 {diff:+.1f}%")

    # 分 struct / focus / scene 单独看，找哪一层真的带信号
    print("\n分层单独检验（比例 = 该层同组更近的概率，0.5 无用）:")
    for key in ("struct", "focus", "scene"):
        val = {r["id"]: r[key] for r in rows}
        s_ = []; x_ = []
        guard = 0
        while (len(s_) < 1200 or len(x_) < 1200) and guard < 400000:
            guard += 1
            a, b = random.sample(ids, 2)
            if lb[a] != lb[b]:
                continue
            d = dtw(seqs[a], seqs[b])
            if d is None:
                continue
            (s_ if val[a] == val[b] else x_).append(d)
        w = 0
        for _ in range(1500):
            i, j = np.random.randint(len(s_)), np.random.randint(len(x_))
            w += s_[i] < x_[j]
        print(f"  {key:7s} 同组中位={np.median(s_):.3f} 异组中位={np.median(x_):.3f}  "
              f"P(同组更近)={w/1500:.3f}")


if __name__ == "__main__":
    main()
