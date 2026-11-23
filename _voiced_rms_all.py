# -*- coding: utf-8 -*-
"""重算交付目录 239 条的 voiced RMS（报告口径）。

为什么要单独跑：`gate_report.py` 读 `_voiced_rms.json`，而那是 2026-11-12 19:47 的快照，
之后回填了 r5 21 条 + r6 15 条 —— 报告会拿旧电平做「跨度 ≤1dB」的验收结论。
"""
import json, os, sys
import numpy as np
import soundfile as sf
sys.path.insert(0, "G:/_setup")
from norm_dlg import vdb

OUT = "G:/_setup/_audio_ch123/out"
plan = {json.loads(l)["id"]: json.loads(l)
        for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8") if l.strip()}
res = {}
for i in sorted(plan):
    p = os.path.join(OUT, i + ".wav")
    if not os.path.exists(p):
        res[i] = None
        continue
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    res[i] = round(float(vdb(y, sr)), 2)
json.dump(res, open("G:/_setup/_voiced_rms.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
v = sorted(x for x in res.values() if x is not None)
print("voiced RMS %d 条：min %.2f 中位 %.2f max %.2f 跨度 %.2f dB"
      % (len(v), v[0], v[len(v) // 2], v[-1], v[-1] - v[0]))
print("缺文件:", [k for k, x in res.items() if x is None] or "无")
