# -*- coding: utf-8 -*-
"""量真人切片（E:/ttsds/data/ref_human，159 条）的句中语速，作为目标锚点。

用与交付音频完全相同的 _speedlib 口径，避免两把尺子。
"""
import glob
import io
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _speedlib import speech_time  # noqa: E402

m = json.load(io.open("G:/_setup/_anchor_meta.json", encoding="utf-8"))
files = sorted(glob.glob("E:/ttsds/data/ref_human/*.wav"))
rows = []
for p in files:
    b = os.path.basename(p)
    wid = b.split("___")[0][2:]          # h_w0000___xxx.wav -> 0000
    key = None
    for k in m:
        if str(k).endswith(wid):
            key = k
            break
    if key is None:
        continue
    txt = m[key].get("text") or ""
    nw = len([w for w in re.split(r"\s+", txt.strip()) if w])
    if nw < 4:
        continue
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    res = speech_time(y, sr)
    d, sp = res[0], res[1]
    if sp < 0.3:
        continue
    rows.append(dict(wid=wid, nw=nw, dur=d, speech=sp,
                     wpm=nw / sp * 60.0, share=sp / d))

w = [r["wpm"] for r in rows]
print("真人切片参与统计 %d 条（原 159）" % len(w))
print("句中语速 p10/p25/p50/p75/p90 = %.0f / %.0f / %.0f / %.0f / %.0f"
      % tuple(np.percentile(w, [10, 25, 50, 75, 90])))
print("语音占比 中位 %.3f  p10 %.3f  p90 %.3f"
      % (float(np.median([r["share"] for r in rows])),
         float(np.percentile([r["share"] for r in rows], 10)),
         float(np.percentile([r["share"] for r in rows], 90))))
fin = [r["wpm"] * r["share"] for r in rows]
print("成品口径（句中×占比）中位 %.0f wpm" % float(np.median(fin)))
print()
print("最快 6 条：")
for r in sorted(rows, key=lambda x: -x["wpm"])[:6]:
    print("   %s %2d词 %.2fs 句中 %.0f" % (r["wid"], r["nw"], r["speech"], r["wpm"]))
print("最慢 6 条：")
for r in sorted(rows, key=lambda x: x["wpm"])[:6]:
    print("   %s %2d词 %.2fs 句中 %.0f" % (r["wid"], r["nw"], r["speech"], r["wpm"]))

json.dump(rows, io.open("G:/_setup/_human_speed.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
