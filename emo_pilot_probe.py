# -*- coding: utf-8 -*-
"""emo_pilot_probe.py —— 补测 pilot 的物理量，回答「标签到底改了什么」。

emo_pilot_eval 只看 e2v 分类分，结果 emo 相对 ctl 几乎不动（+0.003~0.023）。
但时长动了 0.62~2.69 倍 ⇒ 必须先分清三种可能：
  A 标签没进模型（文本被剥掉了）      → F0/时长都不该变
  B 标签进了但只改时长，F0 不动        → 情绪分不动是合理的（e2v 不吃时序）
  C 标签改了 F0，但 e2v 这个尺子不认   → 尺子问题，不能判标签无效

测三样物理量 + e2v 全维度（看分数跑到哪一类去了）：
  f0_med / f0_span(p10-p90) / voiced_ratio / dur / speech_dur(扣静音)
"""
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")

import numpy as np
import soundfile as sf
import parselmouth

OUT = "G:/_setup/_emo_pilot"
RES = "G:/_setup/_emo_pilot_eval.json"
DST = "G:/_setup/_emo_pilot_probe.json"

FLOOR, CEIL = 50.0, 400.0


def f0_stats(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    pt = snd.to_pitch(time_step=0.005, pitch_floor=FLOOR, pitch_ceiling=CEIL)
    f = pt.selected_array["frequency"]
    f = f[f > 0]
    if len(f) < 5:
        return {"f0_med": None, "f0_span": None, "voiced_ratio": 0.0}
    p10, p50, p90 = np.percentile(f, [10, 50, 90])
    dur = len(pt.selected_array["frequency"]) * 0.005
    return {"f0_med": round(float(p50), 1),
            "f0_p10": round(float(p10), 1),
            "f0_p90": round(float(p90), 1),
            "f0_span": round(float(p90 - p10), 1),
            "voiced_ratio": round(float(len(f) * 0.005 / max(dur, 1e-6)), 3)}


def main():
    rows = json.load(open(RES, encoding="utf-8"))
    from ser import E2V
    print("加载 e2v …", flush=True)
    e2v = E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")

    out = []
    for r in rows:
        rec = {"id": r["id"], "who": r["who"], "emo": r["emo"], "cells": {}}
        for c in ("src", "ctl", "emo"):
            x = r["cells"].get(c)
            if not x:
                continue
            p = x["path"]
            d = f0_stats(p)
            sc = e2v.score(p) or {}
            d["top"] = sc.pop("_top", None)
            d["scores"] = dict(sorted(sc.items(), key=lambda kv: -kv[1])[:4])
            d["dur"] = x["dur"]
            d["silent"] = x["silent"]
            d["speech"] = round(x["dur"] * (1 - x["silent"]), 2)
            d["e2v_val"] = (x.get("res") or {}).get("value")
            rec["cells"][c] = d
        out.append(rec)
        e, f = rec["cells"].get("ctl"), rec["cells"].get("emo")
        if e and f:
            print("%-9s %-4s | F0 %5s→%5s (%+5.1f) span %5s→%5s | 语音 %4.2f→%4.2f (%+3.0f%%) | top %s→%s | %s %.3f→%.3f"
                  % (rec["id"], rec["emo"],
                     e["f0_med"], f["f0_med"], (f["f0_med"] or 0) - (e["f0_med"] or 0),
                     e["f0_span"], f["f0_span"],
                     e["speech"], f["speech"], (f["speech"] / e["speech"] - 1) * 100 if e["speech"] else 0,
                     e["top"], f["top"], e2v.name, e["e2v_val"] or 0, f["e2v_val"] or 0), flush=True)

    json.dump(out, open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", DST)


if __name__ == "__main__":
    main()
