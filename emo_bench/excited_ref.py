#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 Expresso 的 happy / laughing 素材打 VAD，筛出能当「兴奋档 ref」的片段。

判据来自 REPORT_EMOTION_JUDGE.md §10.4.2：
  要生成后 V ≥ 0.410（→ A×V ≥ P25=0.374），ref 原声必须 **V ≥ 0.608**，
  且为了保住 A（生成后 ~0.89），ref 还得高唤醒 **A ≥ 0.75**。
  现有 8 档法语 ref 最高只有 V=0.511，数学上不可能达标 —— 只能换真人兴奋素材。

输出：out/excited_refs.json（候选表，按 A×V 降序）
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

WAV = os.path.join(HERE, "wav", "expresso")
OUT = os.path.join(HERE, "out", "excited_refs.json")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", default="happy,laughing",
                    help="逗号分隔，从 wav/expresso 里按风格筛")
    ap.add_argument("--src", default=WAV, help="wav 目录")
    ap.add_argument("--vmin", type=float, default=0.608)
    ap.add_argument("--amin", type=float, default=0.75)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    import ser as S
    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    files = sorted(f for f in os.listdir(args.src) if f.endswith(".wav")
                   and any(f"__{s}__" in f for s in styles))
    if not files:
        sys.exit(f"{args.src} 里没有 {styles} 素材")
    print(f"{args.src} 命中 {len(files)} 条（{','.join(styles)}），开始打 VAD …")
    m = S.VoxDim()
    rows = []
    t0 = time.time()
    for i, f in enumerate(files, 1):
        p = os.path.join(args.src, f)
        try:
            sc = m.score(p) or {}
        except Exception as e:
            print(f"  [skip] {f}: {e}")
            continue
        A = float(sc.get("arousal", 0))
        V = float(sc.get("valence", 0))
        D = float(sc.get("dominance", 0))
        rows.append({"file": f, "path": p, "A": round(A, 3), "V": round(V, 3),
                     "D": round(D, 3), "AxV": round(A * V, 4),
                     "ok_V": V >= args.vmin, "ok_A": A >= args.amin})
        if i % 10 == 0:
            print(f"  {i}/{len(files)}  {time.time()-t0:.0f}s", flush=True)

    rows.sort(key=lambda r: -r["AxV"])
    good = [r for r in rows if r["ok_V"] and r["ok_A"]]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"criteria": {"V_min": args.vmin, "A_min": args.amin},
                   "total": len(rows), "qualified": len(good),
                   "all": rows, "good": good}, f, ensure_ascii=False, indent=1)

    print(f"\n{len(rows)} 条已评分，**达标 {len(good)} 条**（V≥{args.vmin} 且 A≥{args.amin}）")
    print(f"{'file':52s} {'A':>6} {'V':>6} {'D':>6} {'A*V':>7}")
    for r in rows[:15]:
        flag = "★" if (r["ok_V"] and r["ok_A"]) else " "
        print(f"{flag}{r['file'][:50]:52s} {r['A']:6.3f} {r['V']:6.3f} {r['D']:6.3f} {r['AxV']:7.3f}")
    print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
