# -*- coding: utf-8 -*-
"""看指定条在 v46 与最终分档里的落点，以及音频基本指标。"""
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

S = "G:/_setup"
IDS = sys.argv[1:] or ["c2_0487", "c1_0021", "c1_0046", "c2_0325", "c2_0312"]

g = {os.path.basename(x["wav"])[:-4]: x for x in json.load(open(os.path.join(S, "_gate_dlg_v46.json"), encoding="utf-8"))}
fin = {x["id"]: x for x in json.load(open(os.path.join(S, "_dlg_final.json"), encoding="utf-8"))}
for i in IDS:
    x = g.get(i, {})
    e = x.get("emo_res") or {}
    p = os.path.join(S, "_audio_ch123", "out_paused", i + ".wav")
    dur = sf.info(p).duration if os.path.exists(p) else 0
    print("%-9s %-7s dur=%.2f emo=%s/%s  final=%s  reasons=%s" % (
        i, x.get("verdict"), dur, e.get("value"), e.get("tier"),
        (fin.get(i) or {}).get("bucket"), [r["code"] for r in (x.get("reasons") or [])]))
