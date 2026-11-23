# -*- coding: utf-8 -*-
"""书级分析（读 book_judge.json，不重新打分）

修正了第一版的三个口径错误：
  1. AUC 是排序指标 ⇒ 全书 z 与 raw 的 AUC **必然完全相同**（单调变换不改排序）。
     「书内归一能提高区分力」在排序类指标上不成立，这是数学，不是实验结论。
  2. 第一版 A+0.5·跨度 用的是未标准化原值，跨度单位是 Hz(几十)、A 是 0~1，
     相加等于只有跨度在起作用。必须各自 z 化后再加权。
  3. 相邻句 |Δ| 一栏 raw 用绝对单位、character 用 σ，混着比。统一成 σ。
"""
import json
import os
from collections import defaultdict

import numpy as np

NP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "book_judge.json")


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def main():
    d = json.load(open(NP, encoding="utf-8"))
    rows = d["rows"]
    m = d["metrics"]
    A = np.array(m["A"]["raw"])
    span = np.array(m["span"]["raw"])
    D = np.array(m["D"]["raw"])
    lab = np.array([r["emo"] or "-" for r in rows])
    who = np.array([r["who"] for r in rows])
    dur = np.array([r["dur"] for r in rows])

    # 书内 z（单调）与按角色 z（分组）
    Az = (A - A.mean()) / A.std(ddof=1)
    sz = (span - span.mean()) / span.std(ddof=1)
    Dz = (D - D.mean()) / D.std(ddof=1)
    Ac = np.array(m["A"]["character"])
    sc = np.array(m["span"]["character"])
    Dc = np.array(m["D"]["character"])

    print("=" * 92)
    print("一、先纠正一个方法论：书内 z 归一**不可能**改善任何排序类指标")
    print("  AUC 只看名次；z = (x−μ)/σ 是单调变换，名次不变 ⇒ AUC 逐位相同。")
    print("  实测核对：raw A AUC %.4f / book z A AUC %.4f（应为相等）"
          % (auc(A[lab == "sad"], A[lab == "calm"]),
             auc(Az[lab == "sad"], Az[lab == "calm"])))
    print("  ⇒ 书内归一的真实价值在于**可读性与跨书可比**（把 0.32 换算成「比本书中位低 Xσ」），")
    print("     不是提高区分力。要改区分力只能改**分组方式**（按角色/按场景）。")

    print("\n" + "=" * 92)
    print("二、区分力：预期 sad(%d) vs calm(%d)" % ((lab == "sad").sum(), (lab == "calm").sum()))
    print("  口径：raw(绝对) / char(按角色 z)；两者都是排序口径，可比")
    print("  %-14s %-8s %-8s %-8s %-10s" % ("组合", "raw", "char", "变化", "判读"))
    combos = [("A", A, Ac), ("F0跨度", span, sc), ("D", D, Dc),
              ("A+跨度", Az + sz, Ac + sc),
              ("A+0.5·跨度", Az + 0.5 * sz, Ac + 0.5 * sc),
              ("A+D", Az + Dz, Ac + Dc)]
    for name, v0, v1 in combos:
        a0 = max(auc(v0[lab == "sad"], v0[lab == "calm"]),
                 1 - auc(v0[lab == "sad"], v0[lab == "calm"]))
        a1 = max(auc(v1[lab == "sad"], v1[lab == "calm"]),
                 1 - auc(v1[lab == "sad"], v1[lab == "calm"]))
        dl = a1 - a0
        tag = "按角色归一更好" if dl > 0.03 else ("变差" if dl < -0.03 else "无差别")
        print("  %-14s %-8.3f %-8.3f %+-8.3f %-10s" % (name, a0, a1, dl, tag))

    print("\n  参照：A 单轴 0.70 意味着随机抽一条 sad 和一条 calm，70% 概率 sad 的强度更高。")
    print("  同一模型在 Expresso 真人表演上：happy vs sad A AUC = **0.991**（90/94 条），")
    print("  laughing vs sad = 1.000 ⇒ 模型本身极敏感，"
          "**书内信号弱不是模型不行，是成品里真的没那么多差别**。")

    print("\n" + "=" * 92)
    print("三、有序性：预期情绪的平均落点（同角色 z）")
    for scope, v in (("raw", A), ("char", Ac)):
        line = []
        for e in ("sad", "calm", "happy"):
            mm = lab == e
            line.append("%s %+.2f" % (e, v[mm].mean()) if mm.sum() else "%s n/a" % e)
        print("  %-6s %s" % (scope, "   ".join(line)))
    print("  ★ 注意方向：**sad 的强度高于 calm**。这不是标签错了，是有声书的常态——")
    print("    对话里的「难过」比叙述的「平静」更用力；所以「sad 应比 calm 低」这个直觉本身不适用。")

    print("\n" + "=" * 92)
    print("四、动态范围：这本书 vs 真人语料（这是「适合给有声书评分吗」最直接的答案）")
    print("  真人 745 条：A p10 0.30 / p90 0.67 → 范围 **0.37**（说话人内中位 0.36）")
    print("               跨度 p10 65 / p90 208 Hz")
    print("  %-6s %-5s %-22s %-24s" % ("角色", "n", "A p10/p90（范围）", "跨度 p10/p90"))
    for w in sorted(set(who)):
        mm = who == w
        a = A[mm]
        s = span[mm]
        rng = np.percentile(a, 90) - np.percentile(a, 10)
        print("  %-6s %-5d %.2f / %.2f（**%.2f**，真人的 %.0f%%）  %.0f / %.0f Hz（真人的 %.0f%%）"
              % (w, mm.sum(), np.percentile(a, 10), np.percentile(a, 90), rng,
                 100 * rng / 0.37,
                 np.percentile(s, 10), np.percentile(s, 90),
                 100 * (np.percentile(s, 90) - np.percentile(s, 10)) / (208 - 65)))
    print("\n  ⇒ **这本书的动态范围只有真人的 3-5 成**，这是可以直接下的结论，且不依赖情绪分类对不对。")

    print("\n" + "=" * 92)
    print("五、句间对比：有声书的表达力在「相对相邻句」")
    for name, v in (("raw σ", Az), ("char σ", Ac)):
        dz = []
        for w in set(who):
            idx = [i for i in range(len(rows)) if who[i] == w]
            dz += [abs(v[idx[j + 1]] - v[idx[j]]) for j in range(len(idx) - 1)]
        dz = np.array(dz)
        print("  %-8s 相邻同角色 |ΔA| 中位 %.2fσ  p90 %.2fσ   ≤0.3σ（听不出差别）占 %.0f%%"
              % (name, np.median(dz), np.percentile(dz, 90), 100 * (dz <= 0.3).mean()))
    print("  raw σ 与 char σ 几乎相同（0.75 vs 0.73）不是巧合：")
    print("  同角色内相邻句的 Δ(A−μ_w) 恒等于 ΔA，去掉角色均值根本不改变差值，只改了除数（该角色 SD）。")
    print("  ⇒ 第一版报的「raw 0.07σ vs char 0.73σ」是**单位混用**造成的假象（绝对单位 vs σ），已作废。")
    print("  ⇒ 结论：判句间对比用 raw σ 即可，按角色去均值不会让起伏「变大」。")

    print("\n" + "=" * 92)
    print("六、可信度告警（书级结论必须带）")
    print("  <3s 的句子 %d/%d = %.0f%%（模型训练时滤掉 <3s，作者自标不可靠）"
          % ((dur < 3).sum(), len(dur), 100 * (dur < 3).mean()))
    print("  A 全落在 [%.2f, %.2f]，模型输出上限 0.82 ⇒ 整本书都在中性偏下，" % (A.min(), A.max()))
    print("    **无法判断「有没有演过头」**（天花板根本够不到）")
    print("  生产链 −24dBFS 归一后 speech_db 只剩 3.2dB 跨度 ⇒ 音量轴已不可用")


if __name__ == "__main__":
    main()
