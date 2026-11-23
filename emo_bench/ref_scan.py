#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 ref 扫描器：给任意目录/风格的素材批量打 VAD，按指定判据筛 ref 候选。

为什么不复用 excited_ref.py：那个把判据写死成 A×V≥阈值 & A≥阈值（兴奋专用）。
紧张/警惕/平静的判据完全不同（A×(1−D) / e2v disgusted / V），而且素材在
原始数据集里是递归目录（splitted_conversation/**/<style>/<clip>/*.wav），
不是切好的扁平 wav/expresso。这里统一成「递归收集 + 任意判据 + 分位对照」。

判据名与 verdict.py 的 PRIMARY 一致，另加派生量：
  a_x_v   = A*V          兴奋
  a_x_nd  = A*(1-D)      紧张 / 警惕(secondary)
  neg_a   = 1-A          委屈
  d       = D            激动反抗
  v       = V            平静

用法：
  python ref_scan.py --styles fearful,whisper --crit a_x_nd --emo 紧张
  python ref_scan.py --styles calm,sleepy --crit v --emo 平静 --src-root <root>
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

ROOT = "G:/_setup/datasets/ExpressiveSpeech/audios/Expresso/splitted_conversation"
STATS = os.path.join(HERE, "out", "ref_stats.json")

DERIVED = {
    "a_x_v": lambda A, V, D: A * V,
    "a_x_nd": lambda A, V, D: A * (1 - D),
    "neg_a": lambda A, V, D: 1 - A,
    "neg_a_neg_v_neg_d": lambda A, V, D: (1 - A) * (1 - V) * (1 - D),
    "a_x_v_x_d": lambda A, V, D: A * V * D,
    "d": lambda A, V, D: D,
    "v": lambda A, V, D: V,
    "a": lambda A, V, D: A,
}


def collect(root, styles):
    out = []
    for st in styles:
        out += glob.glob(os.path.join(root, "**", f"*{st}*", "**", "*.wav"), recursive=True)
    # 目录名匹配可能太宽（sad 会命中 sympathetic-sad），收紧成路径里确实含该风格目录
    keep = []
    for p in out:
        parts = p.replace("\\", "/").split("/")
        if any(any(st in d.split("_") for d in parts[:-1]) or
               any(d.endswith("_" + st) or d == st or ("_" + st + "_") in d for d in parts[:-1])
               for st in styles):
            keep.append(p)
    return sorted(set(keep))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", required=True, help="逗号分隔风格名")
    ap.add_argument("--crit", required=True, choices=sorted(DERIVED))
    ap.add_argument("--emo", default="", help="对应情绪名，用来读 ref_stats 的 P25/P50 对照")
    ap.add_argument("--src-root", default=ROOT)
    ap.add_argument("--min", type=float, default=None, help="判据下限，默认取 P25")
    ap.add_argument("--min-a", type=float, default=0.0, help="额外要求 A 下限")
    ap.add_argument("--min-dur", type=float, default=1.5)
    ap.add_argument("--max-dur", type=float, default=12.0)
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 条（调试）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import soundfile as sf
    import ser as S

    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    files = collect(args.src_root, styles)
    if args.limit:
        files = files[:args.limit]
    if not files:
        sys.exit(f"没找到 {styles} 素材")

    # 先按时长过滤，省掉明显不合适的（太短撑不住 ref，太长混多句）
    kept = []
    for p in files:
        try:
            d = sf.info(p).duration
        except Exception:
            continue
        if args.min_dur <= d <= args.max_dur:
            kept.append((p, d))
    files = kept

    P25 = P50 = None
    if args.emo and os.path.exists(STATS):
        stats = json.load(open(STATS, encoding="utf-8"))
        sig = stats.get(args.emo, {}).get("signals", {})
        key = next((k for k in sig if k.split(":")[-1] == args.crit), None)
        if key:
            P25 = sig[key]["pos"].get("p25")
            P50 = sig[key]["pos"].get("p50")
    lo = args.min if args.min is not None else (P25 or 0.0)

    print(f"扫 {len(files)} 条（{','.join(styles)}），判据 {args.crit} "
          f"下限 {lo:.4f}（P25={P25} P50={P50}）…", flush=True)

    m = S.VoxDim()
    fn = DERIVED[args.crit]
    rows, t0 = [], time.time()
    for i, (p, dur) in enumerate(files, 1):
        try:
            sc = m.score(p) or {}
        except Exception as e:
            print(f"  [skip] {os.path.basename(p)}: {e}")
            continue
        A = float(sc.get("arousal", 0))
        V = float(sc.get("valence", 0))
        D = float(sc.get("dominance", 0))
        rows.append({"file": os.path.basename(p), "path": p, "dur": round(dur, 2),
                     "A": round(A, 3), "V": round(V, 3), "D": round(D, 3),
                     "a_x_v": round(A * V, 4), "a_x_nd": round(A * (1 - D), 4),
                     "neg_a": round(1 - A, 4)})
        rows[-1]["score"] = round(fn(A, V, D), 4)
        if i % 20 == 0:
            print(f"  {i}/{len(files)}  {time.time()-t0:.0f}s", flush=True)

    rows.sort(key=lambda r: -r["score"])
    good = [r for r in rows if r["score"] >= lo and r["A"] >= args.min_a]

    out = args.out or os.path.join(HERE, "out", f"refscan_{'_'.join(styles)}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"crit": args.crit, "emo": args.emo, "threshold": lo,
               "p25": P25, "p50": P50, "styles": styles,
               "total": len(rows), "qualified": len(good),
               "all": rows, "good": good},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n{len(rows)} 条已评分，**达标 {len(good)} 条**（{args.crit} ≥ {lo:.4f}）")
    print(f"{'file':30s} {'dur':>5s} {'A':>6s} {'V':>6s} {'D':>6s} {args.crit:>8s}")
    for r in rows[:20]:
        flag = "★" if r["score"] >= lo and r["A"] >= args.min_a else " "
        print(f"{flag}{r['file'][:28]:30s} {r['dur']:5.2f} {r['A']:6.3f} {r['V']:6.3f} "
              f"{r['D']:6.3f} {r['score']:8.3f}")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
