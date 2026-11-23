# -*- coding: utf-8 -*-
"""诊断：句内 prominence 最高的词（top1）落在虚词上，是真错位还是 CWT 测量偏差？

    python _top1_check.py

三个判据：
  1. 位置   —— top1 在句子的第几个词。句首集中在开头 ⇒ F0 重置偏差。
  2. 差距   —— top1 与最高内容词的 prominence 差。差小 ⇒ 并列，不是落错。
  3. 越界   —— 虚词 top1 的绝对值是否真的高（> 全库中位）。
"""
import glob
import os
import statistics
from collections import Counter

PROM_DIR = "G:/_setup/_wpt_out"
PUNCT = set(".,;:!?-\"'()[]—–")

FUNC = set("""a an the and or but nor so yet for if because as than that this these those
i you he she it we they me him her us them my your his its our their mine yours hers ours theirs
am is are was were be been being do does did done have has had having
will would shall should can could may might must ought
to of in on at by with from into onto about over under between among through during before after
up down out off again further then once here there when where why how all any both each few more
most other some such no not only own same too very just also even still yet ever never always
sir madam mr mrs miss""".split())


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 6:
            continue
        try:
            rows.append((f[3], float(f[4])))
        except ValueError:
            continue
    return [(w, p) for w, p in rows if w and w not in PUNCT]


def norm(w):
    return w.lower().strip(".,;:!?\"'()[]—–")


def main():
    files = sorted(glob.glob(os.path.join(PROM_DIR, "*.prom")))
    sents = [s for s in (load(f) for f in files) if len(s) >= 4]
    print(f"sentences: {len(sents)}  words: {sum(len(s) for s in sents)}")

    all_p = [p for s in sents for _, p in s]
    print(f"prominence 全库中位 {statistics.median(all_p):.2f}  p75 {statistics.quantiles(all_p, n=4)[2]:.2f}")

    cases = []
    n_bad = 0
    for s in sents:
        vals = [p for _, p in s]
        top = max(range(len(s)), key=lambda i: vals[i])
        tw = norm(s[top][0])
        if tw in FUNC:
            n_bad += 1
            content = [(p, w) for w, p in s if norm(w) not in FUNC]
            best_c = max(content) if content else (0.0, "")
            cases.append({
                "n": len(s),
                "pos": top,
                "rel": top / max(1, len(s) - 1),
                "word": s[top][0],
                "p": vals[top],
                "gap": vals[top] - best_c[0],
                "cword": best_c[1],
                "rank_of_content": sorted([p for p, _ in content], reverse=True)[:1],
            })

    print(f"\n=== top1 是虚词的句子: {n_bad}/{len(sents)} = {n_bad/len(sents)*100:.1f}% ===")

    if not cases:
        return

    at_head = sum(1 for c in cases if c["pos"] <= 1)
    print(f"其中 top1 在句首 2 个词内: {at_head}/{n_bad} = {at_head/n_bad*100:.1f}%")
    print("相对位置分布 (0=句首 1=句末):")
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)]:
        k = sum(1 for c in cases if lo <= c["rel"] < hi)
        print(f"  {lo:.1f}-{hi:.1f}: {k:3d}  {'#' * (k // 2)}")

    gaps = sorted(c["gap"] for c in cases)
    print(f"\n与最强内容词的 prominence 差: 中位 {statistics.median(gaps):.2f}  p25 {gaps[len(gaps)//4]:.2f}  p75 {gaps[3*len(gaps)//4]:.2f}")
    for lo, hi, lab in [(-99, 0.2, "<=0.2  (并列，不算错)"), (0.2, 0.5, "0.2-0.5 (轻微)"),
                        (0.5, 1.0, "0.5-1.0 (明显)"), (1.0, 99, ">1.0   (硬错位)")]:
        k = sum(1 for g in gaps if lo < g <= hi)
        print(f"  {lab:26s} {k:3d}  {k/len(gaps)*100:4.1f}%")

    absv = sorted(c["p"] for c in cases)
    print(f"\n虚词 top1 的绝对 prominence: 中位 {statistics.median(absv):.2f}")
    print(f"  其中 >1.0（真被强调）: {sum(1 for v in absv if v>1.0)}/{len(absv)} = {sum(1 for v in absv if v>1.0)/len(absv)*100:.1f}%")

    print("\n=== 差最大的 12 条（最可能是真错位）===")
    for c in sorted(cases, key=lambda z: -z["gap"])[:12]:
        print(f"  n={c['n']:2d} pos={c['pos']:2d}  {c['word']:10s} p={c['p']:5.2f}  gap=+{c['gap']:.2f}  vs {c['cword']}")

    print("\n=== 差最小的 8 条（并列，不是错）===")
    for c in sorted(cases, key=lambda z: z["gap"])[:8]:
        print(f"  n={c['n']:2d} pos={c['pos']:2d}  {c['word']:10s} p={c['p']:5.2f}  gap=+{c['gap']:.2f}  vs {c['cword']}")

    print("\n=== 虚词词频 ===")
    for w, k in Counter(norm(c["word"]) for c in cases).most_common(12):
        print(f"  {w:10s} {k}")


if __name__ == "__main__":
    main()
