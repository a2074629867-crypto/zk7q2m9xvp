# -*- coding: utf-8 -*-
"""mt_report.py —— 单章质检报告（读 _mt_score_<ch>.json，不重新分析音频）。

口径全部按项目已固化的阈值：
  电平   ：成品整章 −20dB 真 RMS，句间偏离 ≤1dB
  语速   ：voiced wpm，章内中位 ±15% 内
  F0     ：65–100Hz 为常态带，>305Hz 视为喊叫
  声纹   ：≥0.65（仅统计 ≥2.5s 的条目，短窗不可信）
  ASR    ：相似度 ≥0.90，末词必须在
用法：python mt_report.py --ch ch1
"""
import argparse
import json
import os
from collections import Counter

import numpy as np

ROOT = "G:/_setup"


def q(a, p):
    return float(np.percentile(a, p)) if len(a) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    a = ap.parse_args()
    rows = json.load(open(os.path.join(ROOT, "_mt_score_%s.json" % a.ch), encoding="utf-8"))

    picks, wpm, f0, spk, ratio, durs = [], [], [], [], [], []
    low_conf, misses, f0out = [], [], []
    for r in rows:
        sel = [c for c in r["cands"] if str(c["seed"]) == str(r["pick"])]
        if not sel:
            continue
        c = sel[0]
        picks.append(c)
        wpm.append(c["wpm"]); durs.append(c["dur"]); ratio.append(c["ratio"])
        if c["f0"] > 1:
            f0.append(c["f0"])
            if c["f0"] < 65 or c["f0"] > 100:
                f0out.append((r["id"], round(c["f0"])))
        if c["spk"] == c["spk"] and c["spk"] > 0 and c["dur"] >= 4.0:
            spk.append(c["spk"])
        if not c["tail_ok"] or c["ratio"] < 0.9:
            misses.append((r["id"], round(c["ratio"], 2), c["tail_ok"], r["text"][:60]))
        if len(r["cands"]) > 1 and r["flag"] != "NEED-REGEN":
            sc = sorted([x["score"] for x in r["cands"]], reverse=True)
            if len(sc) > 1 and sc[0] - sc[1] < 0.15:
                low_conf.append(r["id"])

    print("=== %s 质检（%d 单元 / 择优 %d 条）===" % (a.ch, len(rows), len(picks)))
    print("  seed 分布        :", dict(Counter(str(r["pick"]) for r in rows if r.get("pick"))))
    print("  wpm  中位/最快/最慢: %.0f / %.0f / %.0f   p10–p90 %.0f–%.0f"
          % (np.median(wpm), max(wpm), min(wpm), q(wpm, 10), q(wpm, 90)))
    print("  时长 中位         : %.1fs（总 %.1f 分钟）" % (np.median(durs), sum(durs) / 60))
    if f0:
        out = [x for x in f0 if x < 65 or x > 100]
        print("  F0   中位/p10/p90 : %.0f / %.0f / %.0f   出带(<65 或 >100) %d 条 %s"
              % (np.median(f0), q(f0, 10), q(f0, 90), len(out), str(f0out[:6])))
    if spk:
        print("  声纹 中位/最低     : %.3f / %.3f   <0.65 %d 条（共 %d 条可测）"
              % (np.median(spk), min(spk), sum(1 for x in spk if x < 0.65), len(spk)))
    print("  ASR  相似度中位    : %.3f   末词缺失或 <0.90 共 %d 条" % (np.median(ratio), len(misses)))
    print("  候选并列(差距<0.15): %d 条" % len(low_conf))

    worst = sorted(zip([r["id"] for r in rows], picks),
                   key=lambda t: (not t[1]["tail_ok"], t[1]["ratio"]))[:10]
    if misses:
        print("  需关注的条目：")
        for m in misses[:10]:
            print("    %s  r=%.2f tail=%s | %s" % (m[0], m[1], m[2], m[3]))


if __name__ == "__main__":
    main()
