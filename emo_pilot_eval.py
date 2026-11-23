# -*- coding: utf-8 -*-
"""emo_pilot_eval.py —— 给 emo 标签对照实验打分（同一把尺子：dialog_gate 的 gate_emotion）。

三列对照，唯一变量是 <emo>：
  src = 原交付 take（无标签、无 edit 复刻）
  ctl = edit 复刻，无标签      → 剥离「复刻本身」的损伤
  emo = edit 复刻 + <emo>      → 真正要测的效果

判读规则（写死，先定后看）：
  1. 只认 emo 相对 ctl 的变化 —— src→ctl 的差是 edit 复刻的锅，不算标签效果
  2. 声纹必须 ≥0.65（emo 有音色成本，官方实测 0.95→0.77 可接受，0.38 不可接受）
  3. 时长比 emo/src ∈ [0.65, 1.55]（物理硬闸，emo 会缩 8%，短句容易越界）
"""
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")

import dialog_gate as G          # noqa: E402
import ser as S                  # noqa: E402

OUT = "G:/_setup/_emo_pilot"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
RES = "G:/_setup/_emo_pilot_eval.json"


def main():
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            plan[r["id"]] = r

    stats = G.load_ref_stats()
    print("加载 VAD / e2v …", flush=True)
    vox = S.VoxDim()
    e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")
    ev = None

    ids = sorted({f.rsplit("_", 1)[0] for f in os.listdir(OUT) if f.endswith(".wav")})
    rows = []
    for i in ids:
        p = plan.get(i)
        if not p:
            continue
        emo = p["emo"]
        cells = {}
        for cond, path in (("src", G.find_audio(i) if hasattr(G, "find_audio") else None),
                           ("ctl", os.path.join(OUT, i + "_ctl.wav")),
                           ("emo", os.path.join(OUT, i + "_emo.wav"))):
            if cond == "src":
                for c in (os.path.join("G:/_setup/_regen_r2_out", i + ".wav"),
                          os.path.join("G:/_setup/_audio_ch123/out", i + ".wav")):
                    if os.path.exists(c):
                        path = c
                        break
            if not path or not os.path.exists(path):
                continue
            tech = G.audio_stats(path)
            # ref_emo 传 None：这里测的是「这条音频的情绪有多强」，不测「用的档对不对」
            res, verdict, reasons = G.gate_emotion(
                path, emo, stats, vox, e2v, ref_emo=None, dur=tech.get("dur"))
            cells[cond] = {"path": path, "dur": round(tech.get("dur") or 0, 2),
                           "rms": round(tech.get("rms_db") or 0, 1),
                           "peak": round(tech.get("peak") or 0, 3),
                           "silent": round(tech.get("silent") or 0, 3),
                           "res": res, "verdict": verdict}
        rows.append({"id": i, "who": p["who"], "emo": emo, "cells": cells})

    json.dump(rows, open(RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def fmt(c, emo):
        if not c:
            return "   —    "
        r = c["res"] or {}
        if "value" in r:
            return "%6.3f %s" % (r["value"], r["tier"])
        if "A" in r:
            return "A%.2f/V%.2f" % (r["A"], r["V"])
        return "不可测"

    print()
    print("%-8s %-4s %-5s %-16s %-16s %-16s %s"
          % ("id", "who", "emo", "src", "ctl(无标签)", "emo(带标签)", "变化"))
    for r in rows:
        c = r["cells"]
        sv = ((c.get("src") or {}).get("res") or {}).get("value")
        cv = ((c.get("ctl") or {}).get("res") or {}).get("value")
        ev_ = ((c.get("emo") or {}).get("res") or {}).get("value")
        d = ""
        if ev_ is not None and cv is not None:
            d = "%+.3f" % (ev_ - cv)
        print("%-8s %-4s %-5s %-16s %-16s %-16s %s"
              % (r["id"], r["who"], r["emo"],
                 fmt(c.get("src"), r["emo"]), fmt(c.get("ctl"), r["emo"]),
                 fmt(c.get("emo"), r["emo"]), d))
    print("\n结果写进", RES)


if __name__ == "__main__":
    main()
