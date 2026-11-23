# -*- coding: utf-8 -*-
"""_stress_seam.py —— 拆句接缝可行性分析（零生成成本，用现有 545 条数据）。

回答：如果按逗号拆句、各自独立生成再拼，接缝处会有多大落差？

三个量：
  A. 自然逗号处的 F0 落差 vs 句内相邻实词的 F0 落差
     —— 若两者接近，说明模型本来就不在逗号处重置音高，拆句不会额外制造跳变。
  B. 句号处（真句界）的 F0 落差
     —— 这是"自然断句"的上限参考。
  C. declination 强度：后半段首词相对前半段首词低多少
     —— 每段独立生成时，后段首词会回到句中位，落差 ≈ 这个值。
"""
import json
import os
from collections import Counter

import numpy as np

ROOT = "G:/_setup"
PUNC = set(",.;:!?")


def q(a, p):
    a = sorted(a)
    if not a:
        return 0.0
    return a[min(len(a) - 1, max(0, int(round(p * (len(a) - 1)))))]


def main():
    raw = json.load(open(os.path.join(ROOT, "_stress_words.json"), encoding="utf-8"))
    ana = json.load(open(os.path.join(ROOT, "_stress_ch1.json"), encoding="utf-8"))

    within = []        # 句内相邻实词 F0 差
    comma_gap = []     # 逗号两侧实词 F0 差
    period_gap = []    # 句号两侧实词 F0 差
    comma_pause = []   # 逗号"词"的跨度（停顿代理）
    period_pause = []
    decl = []          # 后半段首词 - 前半段首词（半音）
    slope = []         # 整句 F0 对词序的线性斜率（半音/词）

    n_sent = 0
    for path, v in raw.items():
        ws = v.get("words") or []
        if len(ws) < 4:
            continue
        a = ana.get(path)
        if not a or a.get("span_st", 0) < 2.0:
            continue
        fmap = {round(w["start"], 3): w for w in a["words"]}
        # 把 ASR 词序列映射到分析里的 f0_st（按 start 对齐）
        seq = []
        for w in ws:
            k = round(w["start"], 3)
            if k in fmap:
                seq.append(dict(w=w["w"], start=w["start"], end=w["end"],
                                f0=fmap[k]["f0_st"], content=fmap[k]["content"]))
        if len(seq) < 4:
            continue
        n_sent += 1

        # 句内相邻实词
        cont = [s for s in seq if s["content"] and s["w"] not in PUNC]
        for i in range(len(cont) - 1):
            within.append(abs(cont[i + 1]["f0"] - cont[i]["f0"]))

        # 标点两侧
        for i, s in enumerate(seq):
            if s["w"] not in PUNC:
                continue
            prev = next((seq[j] for j in range(i - 1, -1, -1) if seq[j]["content"]), None)
            nxt = next((seq[j] for j in range(i + 1, len(seq)) if seq[j]["content"]), None)
            if not prev or not nxt:
                continue
            d = abs(nxt["f0"] - prev["f0"])
            pause = s["end"] - s["start"]
            if s["w"] == ",":
                comma_gap.append(d)
                comma_pause.append(pause)
            elif s["w"] == ".":
                period_gap.append(d)
                period_pause.append(pause)

        # declination：后半首词 - 前半首词
        if len(cont) >= 4:
            h = len(cont) // 2
            decl.append(cont[h]["f0"] - cont[0]["f0"])
            x = np.arange(len(cont), dtype=float)
            y = np.array([c["f0"] for c in cont], dtype=float)
            if np.std(x) > 0:
                slope.append(float(np.polyfit(x, y, 1)[0]))

    print("=== 样本 %d 条句（%d 条带逗号，%d 条带句号）===" % (n_sent, len(comma_gap), len(period_gap)))
    print()
    print("%-22s %6s %7s %7s %7s %7s" % ("落差（半音）", "n", "中位", "p25", "p75", "p90"))
    for name, arr in (("句内相邻实词", within), ("逗号两侧实词", comma_gap), ("句号两侧实词", period_gap)):
        print("%-22s %6d %7.2f %7.2f %7.2f %7.2f"
              % (name, len(arr), q(arr, .5), q(arr, .25), q(arr, .75), q(arr, .9)))
    print()
    print("=== 停顿代理（标点 token 的跨度，秒）===")
    for name, arr in (("逗号", comma_pause), ("句号", period_pause)):
        print("  %-4s n=%d 中位 %.3f  p25 %.3f  p75 %.3f" % (name, len(arr), q(arr, .5), q(arr, .25), q(arr, .75)))
    print()
    print("=== declination ===")
    print("  后半首词 − 前半首词：中位 %+.2f 半音  p25 %+.2f  p75 %+.2f"
          % (q(decl, .5), q(decl, .25), q(decl, .75)))
    print("  整句 F0 斜率：中位 %+.3f 半音/词  p25 %+.3f  p75 %+.3f"
          % (q(slope, .5), q(slope, .25), q(slope, .75)))
    print()
    cg = q(comma_gap, .5)
    wg = q(within, .5)
    print("=== 结论 ===")
    print("  逗号落差 / 句内落差 = %.2f×" % (cg / wg if wg else 0))
    print("  若接近 1 ⇒ 模型不在逗号处重置音高，拆句拼接的落差与自然落差同量级")


if __name__ == "__main__":
    main()
