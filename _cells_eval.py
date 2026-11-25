# -*- coding: utf-8 -*-
"""
_cells_eval.py —— 用同一套指标比较两种标签来源：spaCy 启发式 vs LLM 标注。

指标三项（与 §18 完全一致，便于对照）：
  1. η²：cell / struct(固定len) / focus(固定len) 解释的方差，300 次置换 p
  2. DTW：同 cell（同长度）vs 跨 cell（同长度）的词间 Δmed 序列距离，P(同cell更近)
  3. τ 与 PASS：同 cell 内两两距离 p90 当容差，看通过率（100% = 判不出 C）

用法: python _cells_eval.py llm|spacy
"""
import json, random, collections, sys
import numpy as np

random.seed(7)
np.random.seed(7)

FEAT_PITCH = ["span_st", "peak_max", "absdmed_p90", "wrange_med"]
MERGED_MIN = 8


def dtw(a, b):
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            D[i, j] = abs(ai - b[j - 1]) + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)


def eta2(vals, labels):
    vals = np.asarray(vals, float)
    g = collections.defaultdict(list)
    for v, l in zip(vals, labels):
        g[l].append(v)
    gm = vals.mean()
    ssb = sum(len(x) * (np.mean(x) - gm) ** 2 for x in g.values())
    sst = ((vals - gm) ** 2).sum()
    return ssb / sst if sst > 0 else 0.0


def perm_p(vals, labels, obs, n=300):
    lab = list(labels); c = 0
    for _ in range(n):
        random.shuffle(lab)
        if eta2(vals, lab) >= obs:
            c += 1
    return c / n


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "llm"
    rows = json.load(open("_cells.json", encoding="utf-8"))["rows"]
    if src == "llm":
        L = json.load(open("_cells_llm.json", encoding="utf-8"))
        for r in rows:
            q = L.get(r["id"])
            if q:
                r["scene"], r["struct"], r["focus"] = q["scene"], q["struct"], q["focus"]
                r["prom"] = q.get("prom")
    print(f"标签来源 = {src}")
    for k in ("scene", "struct", "focus"):
        print(" ", k, dict(collections.Counter(r[k] for r in rows)))

    full = collections.Counter((r["struct"], r["len"], r["focus"]) for r in rows)
    print(f"  cell={len(full)}  ≥{MERGED_MIN}句={sum(1 for v in full.values() if v>=MERGED_MIN)}")

    def lab(r):
        if full[(r["struct"], r["len"], r["focus"])] >= MERGED_MIN:
            return f'{r["struct"]}|{r["len"]}|{r["focus"]}'
        if full[(r["struct"], r["len"], "句末焦点")] >= MERGED_MIN:
            return f'{r["struct"]}|{r["len"]}|句末焦点*'
        return f'{r["struct"]}|{r["len"]}|*'
    for r in rows:
        r["cell"] = lab(r)

    # 1) η²
    print("\nη²（cell / struct|len / focus|len）")
    for d in ("span_st", "wrange_med", "absdmed_med", "absdmed_p90", "peak_max", "slope_med", "dur_med", "wps"):
        sub = [r for r in rows if r[d] is not None]
        v = [r[d] for r in sub]
        e = eta2(v, [r["cell"] for r in sub]); p = perm_p(v, [r["cell"] for r in sub], e, 200)
        ss = [r for r in sub if r["len"] in ("9-17", "18-27")]
        es = ef = ps = pf = None
        if len(ss) >= 80:
            v2 = [r[d] for r in ss]
            es = eta2(v2, [r["struct"] for r in ss]); ps = perm_p(v2, [r["struct"] for r in ss], es, 200)
            ef = eta2(v2, [r["focus"] for r in ss]); pf = perm_p(v2, [r["focus"] for r in ss], ef, 200)
        f = lambda x: "  —" if x is None else f"{x:.3f}"
        print(f"  {d:<13} η²={f(e)} p={p:.2f} | struct η²={f(es)} p={('' if ps is None else f'{ps:.2f}')}"
              f" | focus η²={f(ef)} p={('' if pf is None else f'{pf:.2f}')}")

    # 2) DTW
    P = json.load(open("_prosody5_all.json", encoding="utf-8"))
    seq = {}
    for r in rows:
        s = [p["d_med"] for p in P[f'{r["id"]}|new']["pairs"] if p["d_med"] is not None]
        if len(s) >= 4:
            a = np.array(s, float)
            seq[r["id"]] = (a - a.mean()) / (a.std() + 1e-9)
    rows2 = [r for r in rows if r["id"] in seq]
    ids = [r["id"] for r in rows2]
    cell = {r["id"]: r["cell"] for r in rows2}
    lb = {r["id"]: r["len"] for r in rows2}
    print(f"\nDTW（可用 {len(ids)} 句）")

    def sample(n, same):
        out = []; g = 0
        while len(out) < n and g < n * 300:
            g += 1
            a, b = random.sample(ids, 2)
            if lb[a] != lb[b] or ((cell[a] == cell[b]) != same):
                continue
            out.append(dtw(seq[a], seq[b]))
        return out
    S, X = sample(2500, True), sample(2500, False)
    w = sum(1 for _ in range(2000) if S[np.random.randint(len(S))] < X[np.random.randint(len(X))])
    print(f"  同cell中位={np.median(S):.3f} 跨cell中位={np.median(X):.3f}  P(同cell更近)={w/2000:.3f}")

    # 3) τ 与 PASS
    sub = [r for r in rows2 if all(r.get(f) is not None for f in FEAT_PITCH)]
    Xm = np.array([[r[f] for f in FEAT_PITCH] for r in sub], float)
    Z = (Xm - Xm.mean(0)) / (Xm.std(0) + 1e-9)
    idx = {r["id"]: i for i, r in enumerate(sub)}
    byc = collections.defaultdict(list)
    for r in sub:
        byc[r["cell"]].append(r["id"])
    taus, passes, tot, dmin = [], 0, 0, []
    for c, mem in byc.items():
        if len(mem) < MERGED_MIN:
            continue
        D = np.array([[np.linalg.norm(Z[idx[a]] - Z[idx[b]]) for b in mem] for a in mem])
        tau = float(np.percentile(D[np.triu_indices(len(mem), 1)], 90))
        med = int(np.argmin(D.sum(1)))
        tpl = [mem[med]]
        while len(tpl) < min(3, len(mem)):
            rest = [i for i in range(len(mem)) if mem[i] not in tpl]
            tpl.append(mem[max(rest, key=lambda i: min(np.linalg.norm(Z[idx[mem[i]]] - Z[idx[t]]) for t in tpl))])
        for a in mem:
            d = min(np.linalg.norm(Z[idx[a]] - Z[idx[t]]) for t in tpl)
            dmin.append(d); tot += 1; passes += d <= tau
        taus.append(tau)
    print(f"\nτ/PASS: 覆盖 {tot} 句  τ中位={np.median(taus):.2f}  "
          f"到模板距离中位={np.median(dmin):.2f}  PASS={passes}/{tot} = {passes/max(tot,1)*100:.1f}%")

    json.dump({"src": src, "cells": dict(collections.Counter(r["cell"] for r in rows))},
              open(f"_cells_eval_{src}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
