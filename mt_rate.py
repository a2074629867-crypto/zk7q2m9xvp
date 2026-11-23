# -*- coding: utf-8 -*-
"""mt_rate.py —— 给「太快」的条打 `<rate, factor=0.40>`，把语速压到目标。

**实测标定（同种子 A/B，14 词句）**
| factor | 有声时长 | voiced wpm | 倍数 m |
|---|---|---|---|
| 无     | 3.58s | 235 | 1.00 |
| 0.631  | 3.88s | 216 | 1.08 |
| 0.40   | 4.50s | 187 | 1.26 |

⇒ 效果比 f^-0.5 的直觉弱得多，且与文本有关；能稳定拿到的是 **m ≈ 1.25**。
深度放慢已验证安全：ASR 100% 正确、声纹 0.847（高于换种子的基线 0.775）、有声重心不变。

策略：
- w > T×1.02 且需要 m ≤ 1.30 ⇒ f=0.40（一次到位）
- 需要 m > 1.30 的极端快条 ⇒ 也给 f=0.40（已经到底），残余交给 rubberband
- **比 T 慢的条不打标记**（用户：原声慢的不加快）

用法：python mt_rate.py --ch ch1
"""
import argparse
import json
import os

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
DIRS = ["_mt_raw_s42", "_mt_raw_s1234"]
TARGET_RATIO = 0.80
F_SLOW = 0.40
TRIGGER = 1.02          # 超过目标 2% 才动手


def voiced_wpm(fp, words):
    y, sr = sf.read(fp, dtype="float32", always_2d=True)
    y = y.mean(1)
    w = int(0.02 * sr)
    n = sum(w for i in range(0, len(y) - w, w)
            if 20 * np.log10(np.sqrt((y[i:i + w] ** 2).mean()) + 1e-12) > -40)
    v = n / float(sr)
    return words / v * 60.0 if v > 0.15 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--plan", default="mt_plan2.json")
    ap.add_argument("--target", type=float, default=None)
    a = ap.parse_args()

    plan = [p for p in json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
            if p["ch"] == a.ch]
    meas = {}
    for p in plan:
        w = len(p["text"].split())
        vals = [voiced_wpm(os.path.join(ROOT, d, p["id"] + ".wav"), w)
                for d in DIRS
                if os.path.exists(os.path.join(ROOT, d, p["id"] + ".wav"))]
        vals = [v for v in vals if v > 0]
        if vals:
            meas[p["id"]] = float(np.median(vals))

    tf = os.path.join(ROOT, "_mt_target.json")
    tat = json.load(open(tf, encoding="utf-8")) if os.path.exists(tf) else {}
    T = a.target or tat.get(a.ch) or float(np.median(list(meas.values()))) * TARGET_RATIO
    tat[a.ch] = T
    json.dump(tat, open(tf, "w", encoding="utf-8"), indent=1)

    rate = {}
    for p in plan:
        w = meas.get(p["id"], 0.0)
        rate[p["id"]] = F_SLOW if (w > 0 and w > T * TRIGGER) else 1.0

    tagged = sum(1 for v in rate.values() if v < 0.999)
    out = os.path.join(ROOT, "_mt_rate_%s.json" % a.ch)
    json.dump(rate, open(out, "w", encoding="utf-8"), indent=0)
    print("章 %s：可测 %d/%d  voiced wpm 中位 %.0f  目标 %.0f  打标记 %d 条（不改 %d 条）"
          % (a.ch, len(meas), len(plan), np.median(list(meas.values())), T,
             tagged, len(plan) - tagged))
    print("  → %s" % out)


if __name__ == "__main__":
    main()
