#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把六类情绪的分档证据合成一张表。

数据来源（都已在磁盘上，不重新计算）：
  out/excite_n5.json        兴奋（EXC004b n=6 / L181 n=5）
  out/emo_eval_tense.json   紧张 第一轮（TS1/TS2/TS3/BASE）
  out/emo_eval_tense2.json  紧张 第二轮（TS4/TS5/TS6/BASE）
  out/emo_eval_tense_rate.json  紧张 降速探测
  out/emo_eval_calm.json    平静（PL1/PL2/PL3/BASE）
  out/emo_eval_wary.json    警惕（e2v 通道）
  out/emo_eval_verify.json  委屈 / 激动反抗（复核）

判档口径（来自 REPORT_EMOTION_JUDGE.md 三档法）：
  mean ≥ P25            → 到位
  P10 ≤ mean < P25      → 勉强
  mean < P10            → 没演出来
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

P25 = {"兴奋": 0.3745, "紧张": 0.269, "平静": 0.5154, "警惕": 0.0052,
       "委屈": 0.4934, "激动反抗": 0.6239}
P10 = {"兴奋": 0.247, "紧张": 0.2534, "平静": 0.3963, "警惕": 0.0009,
       "委屈": 0.368, "激动反抗": 0.5407}
CRIT = {"兴奋": "A×V", "紧张": "A×(1−D)", "平静": "V", "警惕": "e2v disgusted",
        "委屈": "1−A", "激动反抗": "D"}


def tier(emo, mean):
    if mean >= P25[emo]:
        return "到位"
    if mean >= P10[emo]:
        return "勉强"
    return "未达"


def load(name):
    p = os.path.join(OUT, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def main():
    rows = []

    # 兴奋
    d = load("excite_n5.json")
    if d:
        import numpy as np
        for g, label in (("EXC004b", "Expresso happy 004_speaker1_22s_24s"),
                         ("L181", "Expresso laughing 00181（已否定）")):
            v = [r["AxV"] for r in d.get(g, [])]
            if not v:
                continue
            mean = float(np.mean(v))
            rows.append(("兴奋", label, len(v), mean, sum(x >= P25["兴奋"] for x in v), tier("兴奋", mean)))

    # 紧张
    for fn, groups in (("emo_eval_tense.json", [("TS1", "fearful 044 'Don't let go of my hand'"),
                                                ("BASE_scold", "E_scold（基线）")]),
                       ("emo_eval_tense2.json", [("TS4", "fearful 021 'He's moving'"),
                                                 ("TS5", "fearful 045 'not letting go'"),
                                                 ("TS6", "fearful 016 'I'm sorry I'm sorry'")]),
                       ("emo_eval_tense_rate.json", [("TR85", "TS1 + rate 0.85"),
                                                     ("TR75", "TS1 + rate 0.75")])):
        d = load(fn)
        if not d:
            continue
        for g, label in groups:
            s = d["summary"].get(g)
            if s:
                rows.append(("紧张", label, s["n"], s["mean"], s["pass"], tier("紧张", s["mean"])))

    # 平静
    d = load("emo_eval_calm.json")
    if d:
        names = {"PL1": "sleepy 023（拖速）", "PL2": "calm 038", "PL3": "calm 046",
                 "BASE_normal": "C_normal（定档）"}
        for g, label in names.items():
            s = d["summary"].get(g)
            if s:
                rows.append(("平静", label, s["n"], s["mean"], s["pass"], tier("平静", s["mean"])))

    # 警惕
    d = load("emo_eval_wary.json")
    if d:
        names = {"WD1": "disgusted 018（定档）", "WD2": "disgusted 012", "WD3": "disgusted 060",
                 "BASE_beg": "E_begging（基线）"}
        for g, label in names.items():
            s = d["summary"].get(g)
            if s:
                rows.append(("警惕", label, s["n"], s["mean"], s["pass"], tier("警惕", s["mean"])))

    # 委屈 / 激动反抗（两个文件各评一种判据，交叉验证互不串档）
    for fn, emo, g in (("emo_eval_verify_sad.json", "委屈", "V_SOFT"),
                       ("emo_eval_verify_angry.json", "激动反抗", "V_ANGRY")):
        d = load(fn)
        if not d:
            continue
        s = d["summary"].get(g)
        if s:
            label = "C_soft（定档）" if emo == "委屈" else "C_angry（定档）"
            rows.append((emo, label, s["n"], s["mean"], s["pass"], tier(emo, s["mean"])))
        # 交叉项：看另一档 ref 在本题上的表现，用来证明「不串档」
        other = "V_ANGRY" if g == "V_SOFT" else "V_SOFT"
        so = d["summary"].get(other)
        if so:
            rows.append((emo, f"（交叉）{'C_angry' if other=='V_ANGRY' else 'C_soft'}",
                         so["n"], so["mean"], so["pass"], tier(emo, so["mean"])))

    order = ["兴奋", "激动反抗", "委屈", "紧张", "警惕", "平静"]
    rows.sort(key=lambda r: order.index(r[0]))

    print(f"{'情绪':8s} {'判据':14s} {'P25':>7s} {'ref':40s} {'n':>2s} {'均值':>7s} {'过线':>5s} 档")
    for emo, label, n, mean, ok, t in rows:
        print(f"{emo:8s} {CRIT[emo]:14s} {P25[emo]:7.3f} {label[:40]:40s} {n:2d} "
              f"{mean:7.3f} {ok:>3d}/{n:<2d} {t}")

    print("\n=== 六类定档（显式指定，不按最大值自动挑）===")
    # 为什么不用 max：紧张那组 rate 0.85 是 n=3 且降速标签实测未生效（时长 2.05→2.03s），
    # 拿它当定档会掩盖「紧张就是上不去」这个事实。定档必须同时满足「n≥5」+「标签有实证效果」。
    CHOSEN = {
        "兴奋": "Expresso happy 004_speaker1_22s_24s",
        "激动反抗": "C_angry（定档）",
        "委屈": "C_soft（定档）",
        "紧张": "fearful 044 'Don't let go of my hand'",
        "警惕": "disgusted 018（定档）",
        "平静": "C_normal（定档）",
    }
    for emo in order:
        label = CHOSEN.get(emo)
        sub = [r for r in rows if r[0] == emo and r[1] == label]
        if not sub:
            continue
        _, label, n, mean, ok, t = sub[0]
        print(f"  {emo:6s} {CRIT[emo]:13s} {label[:40]:40s} n={n} 均值 {mean:.3f} "
              f"过线 {ok}/{n}  → {t}")

    json.dump([dict(emo=r[0], ref=r[1], n=r[2], mean=r[3], pass_n=r[4], tier=r[5]) for r in rows],
              open(os.path.join(OUT, "emo_table.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
