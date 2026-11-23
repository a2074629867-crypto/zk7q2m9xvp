# -*- coding: utf-8 -*-
"""mt_fall.py —— 检测「碎片句被念成完整句」：末段音高是否落到句末调。

原理：真句号结尾会落调（F0 末段明显低于句中）；逗号结尾只应轻微下压。
若逗号结尾的碎片也大幅落调 ⇒ 拼接后会被听成"一句话被切成好几段"。

判据：末 350ms 有声帧 F0 中位 vs 全句 F0 中位
  落差 > 3.5 半音 ⇒ 句末调（对逗号碎片是错的）
用法：python mt_fall.py --ch ch1
"""
import argparse
import json
import os

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
import sys
sys.path.insert(0, ROOT)
import re

END_P = re.compile(r"[.!?\u2026][\u2019\u201d]?$")


def frames(y, sr, lo_f=60, hi_f=400):
    hop, win = int(0.02 * sr), int(0.04 * sr)
    lo, hi = int(sr / hi_f), int(sr / lo_f)
    out = []
    for i in range(0, len(y) - win, hop):
        f = y[i:i + win]
        if np.sqrt((f ** 2).mean()) < 0.01:
            out.append((i / sr, 0.0))
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[win - 1:]
        if ac[0] <= 0:
            out.append((i / sr, 0.0)); continue
        seg = ac[lo:hi] / ac[0]
        if len(seg) < 3 or seg.max() < 0.3:
            out.append((i / sr, 0.0)); continue
        k = int(np.argmax(seg))
        out.append((i / sr, sr / (k + lo)))
    return out


def st(a, b):
    """半音差"""
    if a <= 0 or b <= 0:
        return 0.0
    return 12 * np.log2(a / b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--plan", default="mt_plan3.json")
    a = ap.parse_args()
    plan = [p for p in json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
            if p["ch"] == a.ch]

    rows = []
    for p in plan:
        fp = os.path.join(ROOT, "_mt_pick", p["id"] + ".wav")
        if not os.path.exists(fp):
            continue
        y, sr = sf.read(fp, dtype="float32", always_2d=True)
        y = y.mean(1)
        if len(y) / sr < 0.8:
            continue
        fr = frames(y, sr)
        v = [f for _, f in fr if f > 0]
        if len(v) < 12:
            continue
        med = float(np.median(v))
        tail = v[-20:]                    # 最后 20 个有声帧 ≈ 末 0.4s 语音
        rows.append({"id": p["id"], "end": bool(END_P.search(p["text"].rstrip())),
                     "fall": float(st(med, float(np.median(tail)))), "med": med,
                     "text": p["text"]})

    for label, sel in [("句号结尾", [r for r in rows if r["end"]]),
                       ("逗号结尾（碎片）", [r for r in rows if not r["end"]])]:
        F = np.array([r["fall"] for r in sel])
        deep = (F > 3.5).sum()
        print("%-16s %3d 条   落调中位 %.2f 半音   >3.5 半音（听起来像句号）%3d 条（%.0f%%）"
              % (label, len(sel), np.median(F), deep, 100.0 * deep / max(1, len(sel))))
    bad = sorted([r for r in rows if not r["end"] and r["fall"] > 3.5],
                 key=lambda r: -r["fall"])
    print("\n最像“已经念完”的碎片（应改）：")
    for r in bad[:8]:
        print("  %s  落 %.1f 半音 | %s" % (r["id"], r["fall"], r["text"][-60:]))


if __name__ == "__main__":
    main()
