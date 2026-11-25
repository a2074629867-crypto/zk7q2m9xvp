# -*- coding: utf-8 -*-
"""
_cells_tmpl.py —— 从 cell 里抽「模板集」并算 τ，同时验证它真的能检索。

用户要求：模板可以有很多种（A、B 都对），所以每个 cell 抽**多个**模板，不是一个。
τ（容差）= 同 cell 内两两距离的 p90 —— 由"已被认可的那批"自己张开，不是我定的数。

验证（这一步决定"有没有用"）：
  留一法：对每句，算 d(同 cell 最近邻) 与 d(同长度档、不同 cell 最近邻)
  - 若同 cell 明显更近 ⇒ 分类有检索价值
  - 若五五开 ⇒ 这套分类对检索无用，只能当描述

两种特征集分开跑：
  A 全部 6 维（含 dur/wps）—— 会把我们自己的变速规则混进来
  B 只用音高 4 维 —— 干净的韵律
"""
import json, itertools, statistics as st
import numpy as np

FEAT_ALL = ["span_st", "peak_max", "absdmed_p90", "wrange_med", "dur_med", "wps"]
FEAT_PITCH = ["span_st", "peak_max", "absdmed_p90", "wrange_med"]


def load():
    d = json.load(open("_cells.json", encoding="utf-8"))
    return d["rows"]


def matrix(rows, feats):
    sub = [r for r in rows if all(r.get(f) is not None for f in feats)]
    X = np.array([[r[f] for f in feats] for r in sub], float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    return sub, Z


def loo_test(sub, Z, seed=0):
    """两种口径都报：
       mean  —— 到同 cell 全部其他句的平均距离 vs 到跨 cell（同长度档）的平均距离（与集合大小无关）
       match —— 最近邻距离，但把对照集合按样本量配平（随机抽同数量，20 次平均）
    """
    rng = np.random.default_rng(seed)
    same_m, diff_m, same_k, diff_k = [], [], [], []
    for i, r in enumerate(sub):
        idx_same = [j for j, q in enumerate(sub) if j != i and q["cell"] == r["cell"]]
        idx_diff = [j for j, q in enumerate(sub) if q["cell"] != r["cell"] and q["len"] == r["len"]]
        if not idx_same or not idx_diff:
            continue
        ds = np.linalg.norm(Z[idx_same] - Z[i], axis=1)
        dd = np.linalg.norm(Z[idx_diff] - Z[i], axis=1)
        same_m.append(ds.mean()); diff_m.append(dd.mean())
        # 配平最近邻
        m = min(len(idx_same), len(idx_diff))
        same_k.append(ds.min())
        diff_k.append(np.mean([np.sort(rng.choice(dd, m, replace=False))[0] for _ in range(20)]))
    same_m, diff_m = np.array(same_m), np.array(diff_m)
    same_k, diff_k = np.array(same_k), np.array(diff_k)
    return dict(n=len(same_m),
                mean_same=float(same_m.mean()), mean_diff=float(diff_m.mean()),
                closer_mean=float(np.mean(same_m < diff_m) * 100),
                mean_same_k=float(same_k.mean()), mean_diff_k=float(diff_k.mean()),
                closer_knn=float(np.mean(same_k < diff_k) * 100))


def build_templates(sub, Z, cell, k=3):
    idx = [i for i, r in enumerate(sub) if r["cell"] == cell]
    if len(idx) < 8:
        return None
    D = np.zeros((len(idx), len(idx)))
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            D[a, b] = D[b, a] = np.linalg.norm(Z[idx[a]] - Z[idx[b]])
    tau = float(np.percentile(D[np.triu_indices(len(idx), 1)], 90))
    # medoid
    t = [int(np.argmin(D.sum(1)))]
    # 贪心最远点补齐 k 个模板
    while len(t) < min(k, len(idx)):
        rest = [i for i in range(len(idx)) if i not in t]
        t.append(int(max(rest, key=lambda i: min(D[i, j] for j in t))))
    return dict(cell=cell, n=len(idx), tau=round(tau, 3),
                templates=[sub[idx[i]]["id"] for i in t],
                ids=[sub[i]["id"] for i in idx])


def main():
    rows = load()
    out = {}
    for tag, feats in (("all", FEAT_ALL), ("pitch", FEAT_PITCH)):
        sub, Z = matrix(rows, feats)
        r = loo_test(sub, Z)
        print(f"[{tag}] n={r['n']}  平均距离 同cell={r['mean_same']:.2f} 跨cell={r['mean_diff']:.2f} "
              f"⇒ 同cell更近 {r['closer_mean']:.1f}%")
        print(f"      配平最近邻 同cell={r['mean_same_k']:.2f} 跨cell={r['mean_diff_k']:.2f} "
              f"⇒ 同cell更近 {r['closer_knn']:.1f}%")
        cells = sorted({x["cell"] for x in sub})
        T = [build_templates(sub, Z, c) for c in cells]
        T = [t for t in T if t]
        print(f"  可建模板的 cell: {len(T)} 个，覆盖 {sum(t['n'] for t in T)} 句；"
              f"τ 中位={np.median([t['tau'] for t in T]):.2f}")
        out[tag] = dict(loo=r, templates=T, feats=feats)

    json.dump(out, open("_cells_tmpl.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ _cells_tmpl.json")

    print("\n音高 4 维下的模板集（前 6 个 cell）:")
    for t in out["pitch"]["templates"][:6]:
        print(f"  {t['cell']:<28} n={t['n']:3d} τ={t['tau']:.2f} 模板={t['templates']}")


if __name__ == "__main__":
    main()
