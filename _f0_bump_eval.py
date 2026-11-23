# -*- coding: utf-8 -*-
"""_f0_bump_eval.py —— 评估 F0 驼峰改动的三项指标。

1. `loc`      重音是否真的起来了（与全流程同一把尺）
2. 共振峰      F1/F2 中位是否移动 —— 音色/声道长度有没有变
3. 声纹余弦   与原始 take 的音色相似度（只作参考，短句噪声大）

对照组：`--self-test` 产出的纯声码器版（f0 未改），用来把「声码器本身的损失」
和「F0 改动带来的损失」分开。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
import numpy as np
import parselmouth
import spk_embed as SP

import _adv_prom as P
from parselmouth.praat import call


def formants(wav, t0, t1):
    snd = parselmouth.Sound(wav)
    fm = call(snd, "To Formant (burg)", 0.0, 5, 5500, 0.025, 50)
    out = []
    for i in range(1, 5):
        vals = []
        for t in np.arange(t0 + 0.02, t1 - 0.02, 0.01):
            v = call(fm, "Get value at time", i, float(t), "hertz", "linear")
            if v and np.isfinite(v) and v > 0:
                vals.append(v)
        out.append(float(np.median(vals)) if vals else float("nan"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--prom", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--adv", required=True)
    ap.add_argument("--files", nargs="+", required=True, help="label=path ...")
    a = ap.parse_args()

    rows = P.measure_one(a.orig, a.prom, a.text) or []
    hit = [w for w in rows if w["key"] == a.adv.lower()]
    if not hit:
        raise SystemExit("测不到 %s" % a.adv)
    w = hit[-1]
    t0, t1 = w["t0"], w["t1"]
    f_org = formants(a.orig, t0, t1)
    e_org = SP.embed(a.orig)
    print("原始 %s  loc=%+.2f  有声 %.2fs" % (os.path.basename(a.orig), w["loc"], w["voiced"]))
    print("  共振峰 F1-F4: %s" % "  ".join("%.0f" % x for x in f_org))
    print()
    print("%-16s %-8s %-10s %-22s %-9s %s"
          % ("版本", "loc", "Δloc", "共振峰 F1-F4 (Δ%)", "声纹", "ΔF2"))

    for spec in a.files:
        lab, path = spec.split("=", 1)
        if not os.path.exists(path):
            print("%-16s 缺文件" % lab)
            continue
        r = P.measure_one(path, a.prom, a.text) or []
        h = [x for x in r if x["key"] == a.adv.lower()]
        loc = h[-1]["loc"] if h else None
        f = formants(path, t0, t1)
        d = ["%+.0f%%" % (100 * (f[i] - f_org[i]) / f_org[i]) if np.isfinite(f[i]) and np.isfinite(f_org[i]) else "—"
             for i in range(4)]
        c = SP.cos(e_org, SP.embed(path))
        print("%-16s %+-8.2f %+-10s %-22s %-9.3f %s"
              % (lab, loc if loc is not None else float("nan"),
                 "%+.2f" % (loc - w["loc"]) if loc is not None else "—",
                 " ".join("%.0f(%s)" % (f[i], d[i]) for i in range(4)), c, d[1]))


if __name__ == "__main__":
    main()
