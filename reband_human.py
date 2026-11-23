# -*- coding: utf-8 -*-
"""用当前 narr_check.l1_unit 重新标定真人的 energy_span 带。

为什么要重标：`_rhythm_bands.json` 里 narr 的带是 p05=8.9 / p95=22.55 / p50=14.3（n=159），
而 2026-11-11 已经改过 energy_span 的口径（剔除数字静音停顿槽）。旧带是用旧口径算的，
拿旧带判新产品 = 尺子和被测物不是同一把。
⇒ 必须用**同一份代码**重测真人 159 条，才算得出可比的下界。

输出 `_rhythm_bands_human.json`，带 _meta 写明来源与口径。
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import narr_check as NC

HUMAN = "E:/ttsds/data/ref_human/*.wav"
OUT = "G:/_setup/_rhythm_bands_human.json"

spans, f0s, durs = [], [], []
files = sorted(glob.glob(HUMAN))
print("真人切片 %d 条" % len(files))

for f in files:
    try:
        y, sr = sf.read(f, dtype="float32")
    except Exception as e:
        print("  跳过 %s %s" % (os.path.basename(f), e))
        continue
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    d = NC.l1_unit(y, sr)
    if d.get("energy_span") is not None:
        spans.append(d["energy_span"])
    if d.get("f0_med"):
        f0s.append(d["f0_med"])
    durs.append(len(y) / sr)

spans = np.array(spans, dtype=float)
print("\nenergy_span  n=%d  p05=%.1f  p10=%.1f  p25=%.1f  p50=%.1f  p75=%.1f  p95=%.1f"
      % (len(spans), *[np.percentile(spans, q) for q in (5, 10, 25, 50, 75, 95)]))
print("F0 中位 p10=%.1f p50=%.1f p90=%.1f" % tuple(np.percentile(f0s, [10, 50, 90])))
print("时长 p10=%.2fs p50=%.2fs p90=%.2fs" % tuple(np.percentile(durs, [10, 50, 90])))

band = {
    "_meta": {
        "source": "E:/ttsds/data/ref_human (n=%d)" % len(spans),
        "metric": "narr_check.l1_unit 2026-11-11 口径（NPT=21，语音槽 = 相对最大槽 25dB 内）",
        "why": "旧带 _rhythm_bands.json narr p05=8.9/p95=22.55 是自我标定（我们自己的产物），"
               "用它判新产品等于永远判 OK，'起伏不足'这条闸门失效。改用真人切片标定。",
        "npt": NC.NPT,
    },
    "narr": {
        "energy_span": {
            "p05": round(float(np.percentile(spans, 5)), 2),
            "p10": round(float(np.percentile(spans, 10)), 2),
            "p50": round(float(np.percentile(spans, 50)), 2),
            "p95": round(float(np.percentile(spans, 95)), 2),
            "n": int(len(spans)),
        },
        "f0_med": {
            "p10": round(float(np.percentile(f0s, 10)), 1),
            "p50": round(float(np.percentile(f0s, 50)), 1),
            "p90": round(float(np.percentile(f0s, 90)), 1),
        },
    },
}
json.dump(band, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n写 -> %s" % OUT)
