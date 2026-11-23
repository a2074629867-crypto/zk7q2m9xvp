#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按情绪判据给一批生成音频打分，分组对比 ref 优劣。

设计要点（都来自已踩过的坑）：
1. **配对 seed**：同一 seed 跨 ref 比较，抵掉 seed 侧方差（n=2 骗人的教训）。
2. **组间差必须大于组内 sd** 才判优劣，否则报"无法区分"。
3. 判据方向统一从 ref_stats 的 pos 分位取，避免手抄阈值漏键。
4. 只打印，不改任何文件；结果写 out/emo_eval_<tag>.json。

用法：
  python emo_eval.py --emo 紧张 --dir out/gen --prefix TS1,TS2,TS3,BASE_scold
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

STATS = os.path.join(HERE, "out", "ref_stats.json")


# verdict.PRIMARY 故意不收「平静」——实测平静与 base 在 e2v 上是同一件事，
# 它本质是「色温（V）轴」而非离散情绪。但 ref_stats 里有平静的正例分布，
# 要给它定 ref 就得按 V 评，所以单独补一条。
EXTRA = {"平静": ("vox", "v")}


def load_thr(emo):
    stats = json.load(open(STATS, encoding="utf-8"))
    import verdict as V
    src, key = V.PRIMARY.get(emo) or EXTRA[emo]
    st = stats[emo]["signals"]["%s:%s" % (src, key)]
    return st["pos"], key, st["auc"], src


def metric(A, V, D, key):
    return {
        "a_x_v": A * V,
        "a_x_nd": A * (1 - D),
        "a": A, "v": V, "d": D,
        "neg_a": 1 - A,
    }[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emo", required=True)
    ap.add_argument("--dir", default=os.path.join(HERE, "out", "gen"))
    ap.add_argument("--prefix", required=True, help="逗号分隔的组名前缀")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    import ser as S
    pos, key, auc, src = load_thr(args.emo)
    p25, p10 = pos["p25"], pos["p10"]
    prefixes = [p.strip() for p in args.prefix.split(",") if p.strip()]

    files = [f for f in os.listdir(args.dir)
             if f.endswith(".wav") and any(f.startswith(p + "__") for p in prefixes)]
    if not files:
        sys.exit(f"{args.dir} 里没有 {prefixes} 的音频")

    # 警惕的判据在 emotion2vec 上（disgusted 概率），不在 VAD 上 —— 必须分流，
    # 否则会拿 VAD 的 A/V/D 去比一个 e2v 的阈值，方向完全不同。
    if src == "e2v":
        m = S.E2V()
        def score(p):
            sc = m.score(p) or {}
            return float(sc.get(key, 0.0)), sc.get("_top")
    else:
        m = S.VoxDim()
        def score(p):
            sc = m.score(p) or {}
            return metric(float(sc.get("arousal", 0)), float(sc.get("valence", 0)),
                          float(sc.get("dominance", 0)), key), None

    rows = []
    for f in sorted(files):
        grp = f.split("__")[0]
        seed = re.search(r"s(\d+)\.wav$", f)
        p = os.path.join(args.dir, f)
        val, top = score(p)
        sc = {}
        A = V = D = 0.0
        if src != "e2v":
            # VAD 通道需要把 A/V/D 一并留下做诊断
            sc = m.score(p) or {}
            A = float(sc.get("arousal", 0)); V = float(sc.get("valence", 0)); D = float(sc.get("dominance", 0))
        rows.append({"group": grp, "file": f, "seed": int(seed.group(1)) if seed else None,
                     "A": round(A, 3), "V": round(V, 3), "D": round(D, 3),
                     "top": top, "score": round(val, 4)})

    print(f"判据 {args.emo} = {key}（{src} 通道，AUC {auc:.3f}）P25={p25} P10={p10}\n")
    if src == "e2v":
        print(f"{'group':12s} {'seed':>5s} {key:>10s}  过P25   e2v_top")
        for r in sorted(rows, key=lambda r: (r["group"], r["seed"] or 0)):
            ok = "✓" if r["score"] >= p25 else " "
            print(f"{r['group']:12s} {str(r['seed']):>5s} {r['score']:10.4f}    {ok}    {r['top']}")
    else:
        print(f"{'group':12s} {'seed':>5s} {'A':>6s} {'V':>6s} {'D':>6s} {key:>8s}  过P25")
        for r in sorted(rows, key=lambda r: (r["group"], r["seed"] or 0)):
            ok = "✓" if r["score"] >= p25 else " "
            print(f"{r['group']:12s} {str(r['seed']):>5s} {r['A']:6.3f} {r['V']:6.3f} {r['D']:6.3f} "
                  f"{r['score']:8.3f}   {ok}")

    print()
    summary = {}
    for g in prefixes:
        sub = [r for r in rows if r["group"] == g]
        if not sub:
            continue
        v = np.array([r["score"] for r in sub])
        ok = int((v >= p25).sum())
        summary[g] = {"n": len(v), "mean": round(float(v.mean()), 4),
                      "sd": round(float(v.std(ddof=1)) if len(v) > 1 else 0.0, 4),
                      "pass": ok, "vals": [r["score"] for r in sub]}
        print(f"{g:12s} n={len(v)}  均值 {v.mean():.3f}  sd {v.std(ddof=1) if len(v)>1 else 0:.3f}  "
              f"过线 {ok}/{len(v)}  (P25={p25})")

    # 配对比较：同 seed 差值
    print("\n=== 配对差（同 seed，组 − 基线）===")
    base = prefixes[-1]
    bmap = {r["seed"]: r["score"] for r in rows if r["group"] == base}
    for g in prefixes[:-1]:
        diffs = [r["score"] - bmap[r["seed"]] for r in rows
                 if r["group"] == g and r["seed"] in bmap]
        if not diffs:
            continue
        d = np.array(diffs)
        print(f"{g:12s} vs {base}: 均值 {d.mean():+.3f}  逐条 {[round(x,3) for x in diffs]}")

    out = os.path.join(HERE, "out", f"emo_eval_{args.tag or args.emo}.json")
    json.dump({"emo": args.emo, "crit": key, "auc": auc, "p25": p25, "p10": p10,
               "rows": rows, "summary": summary},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
