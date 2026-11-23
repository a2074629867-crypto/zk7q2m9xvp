# -*- coding: utf-8 -*-
"""_stress_tail.py —— 补充分析：句末实词（核心重音）是否被重读。

前一个脚本测的是「全句最突出的词是不是实词」，那个指标长句反而更高
（实词多，随便命中一个都算对）。真正对应「该重的没重」的是**句末实词**：
英语 end-focus，核心重音默认落在句末实词上。

判据：
  tail_rank = 句末最后一个内容词在 prom 排序中的名次（1 = 最高）
  top1 / top3 命中率按句长分档
  F0 跨度分布（检查短句「无重音」是真实还是测量阈值）
"""
import json
import os
import sys

import numpy as np

ROOT = "G:/_setup"


def q(a, p):
    a = sorted(a)
    if not a:
        return 0.0
    return a[min(len(a) - 1, max(0, int(round(p * (len(a) - 1)))))]


def main():
    res = json.load(open(os.path.join(ROOT, "_stress_ch1.json"), encoding="utf-8"))
    rows = []
    for path, v in res.items():
        ws = v["words"]
        tail = None
        for i in range(len(ws) - 1, -1, -1):
            if ws[i]["content"]:
                tail = i
                break
        if tail is None:
            continue
        pr = ws[tail]["prom"]
        rank = 1 + sum(1 for r in ws if r["prom"] > pr)
        top = max(range(len(ws)), key=lambda i: ws[i]["prom"])
        rows.append(dict(uid=v["uid"], seed=v["seed"], n=v["n_plan"], nw=v["n_word"],
                         span=v["span_st"], rank=rank, prom=pr,
                         maxprom=max(r["prom"] for r in ws),
                         pos=top / max(1, len(ws) - 1),
                         tail_pos=tail / max(1, len(ws) - 1)))

    print("=== 句末实词（核心重音）名次，共 %d 条 ===" % len(rows))
    bins = [(0, 7), (8, 10), (11, 13), (14, 17), (18, 99)]
    print("%-8s %5s %8s %8s %8s %8s %8s" % ("句长", "n", "top1%", "top2%", "top3%", "中位名次", "F0跨度中位"))
    for lo, hi in bins:
        sub = [r for r in rows if lo <= r["n"] <= hi]
        if not sub:
            continue
        n = len(sub)
        t1 = 100.0 * sum(1 for r in sub if r["rank"] == 1) / n
        t2 = 100.0 * sum(1 for r in sub if r["rank"] <= 2) / n
        t3 = 100.0 * sum(1 for r in sub if r["rank"] <= 3) / n
        print("%-8s %5d %8.1f %8.1f %8.1f %8.1f %8.2f"
              % ("%d-%d" % (lo, hi), n, t1, t2, t3,
                 float(np.median([r["rank"] for r in sub])),
                 float(np.median([r["span"] for r in sub]))))

    print("\n=== F0 跨度分布（全部）===")
    sp = [r["span"] for r in rows]
    print("  p10 %.2f / 中位 %.2f / p90 %.2f 半音 | <2 半音占 %.1f%%"
          % (q(sp, .1), q(sp, .5), q(sp, .9), 100.0 * sum(1 for x in sp if x < 2) / len(sp)))

    print("\n=== 跨 seed 位置覆盖（每单元覆盖几个不同位置）===")
    by = {}
    for r in rows:
        by.setdefault(r["uid"], []).append(r)
    from collections import Counter
    cov = Counter()
    for u, vs in by.items():
        if len(vs) < 2:
            continue
        ps = [round(v["pos"] / 0.10) for v in vs]
        cov[len(set(ps))] += 1
    tot = sum(cov.values())
    for k in sorted(cov):
        print("  覆盖 %d 个位置: %d 单元 (%.1f%%)" % (k, cov[k], 100.0 * cov[k] / tot))

    print("\n=== 例子（句末实词名次最差的 5 条）===")
    bad = sorted(rows, key=lambda r: -r["rank"])[:5]
    for r in bad:
        print("  %s s%-5s %2d词 句末实词名次 %d/%d  prom %.2f vs 最高 %.2f"
              % (r["uid"], r["seed"], r["nw"], r["rank"], r["nw"], r["prom"], r["maxprom"]))

    # ---------- 权重敏感性：结论会不会因权重而变 ----------
    def rz(x):
        x = np.asarray(x, dtype=np.float64)
        med = float(np.median(x))
        mad = float(np.median(np.abs(x - med)))
        if mad < 1e-9:
            sd = float(np.std(x))
            return (x - med) / sd if sd > 1e-9 else np.zeros_like(x)
        return 0.6734 * (x - med) / mad

    print("\n=== 权重敏感性：句末实词 top1 命中率（%）===")
    schemes = [("F0 0.5 / E 0.3 / 时长 0.2（当前）", 0.5, 0.3, 0.2),
               ("纯 F0", 1.0, 0.0, 0.0),
               ("纯能量", 0.0, 1.0, 0.0),
               ("纯时长", 0.0, 0.0, 1.0),
               ("F0 0.34 / E 0.33 / 时长 0.33", 1 / 3, 1 / 3, 1 / 3)]
    print("%-34s %8s %8s %8s %8s" % ("方案", "0-7", "8-13", "14-17", "18+"))
    for name, wf, we, wd in schemes:
        out = []
        for lo, hi in [(0, 7), (8, 13), (14, 17), (18, 99)]:
            sub = [v for v in res.values() if lo <= v["n_plan"] <= hi]
            if not sub:
                out.append(float("nan"))
                continue
            hit = 0
            for v in sub:
                ws = v["words"]
                tail = None
                for i in range(len(ws) - 1, -1, -1):
                    if ws[i]["content"]:
                        tail = i
                        break
                if tail is None:
                    continue
                f = rz([r["f0_st"] for r in ws])
                e = rz([r["e_db"] for r in ws])
                d = rz([r["dur"] for r in ws])
                p = wf * f + we * e + wd * d
                if int(np.argmax(p)) == tail:
                    hit += 1
            out.append(100.0 * hit / len(sub))
        print("%-34s %8.1f %8.1f %8.1f %8.1f" % (name, out[0], out[1], out[2], out[3]))


if __name__ == "__main__":
    main()
