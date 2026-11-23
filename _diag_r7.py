# -*- coding: utf-8 -*-
"""只读诊断：r7 那 12 条候选为什么只有 2 条落盘。

不写任何音频，只复算 finish_r7 --gate 的拒绝条件，逐条打印。
"""
import json, os, sys
import numpy as np
import soundfile as sf
sys.path.insert(0, "G:/_setup")

import _nat_guard as NG

HERE = "G:/_setup"
OUT = HERE + "/_audio_ch123/out"
CAND = HERE + "/_regen_r7_out"
WPM_LO, WPM_HI = 90, 260

plan = {json.loads(l)["id"]: json.loads(l) for l in open(HERE + "/_dlg_plan_v2.jsonl", encoding="utf-8") if l.strip()}
todos = {x["id"]: x for x in json.load(open(HERE + "/_regen_r7.json", encoding="utf-8"))}
gate = {r["id"]: r for r in json.load(open(HERE + "/_gate_r7_cand.json", encoding="utf-8"))}
old_gate = {x["id"]: x for x in json.load(open(HERE + "/_gate_dlg_v20.json", encoding="utf-8"))}


def wpm(i, d):
    t = (plan.get(i) or {}).get("text", "")
    wc = len([k for k in t.split() if any(c.isalpha() for c in k)])
    return wc / d * 60.0 if d > 0 else 0.0


print("%-8s %-6s %-6s %-5s %-7s %-7s %-6s %s" % ("id", "verdict", "dur老", "dur新", "ratio", "wpm新", "MOS新", "拒因"))
for i, g in gate.items():
    new, old = os.path.join(CAND, i + ".wav"), os.path.join(OUT, i + ".wav")
    if not (os.path.exists(new) and os.path.exists(old)):
        print("%-8s 文件缺" % i); continue
    d1, d2 = sf.info(old).duration, sf.info(new).duration
    y, _ = sf.read(new, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    pk = float(np.abs(y).max())
    bad = []
    if g["verdict"] == "REGEN":
        bad.append("闸门REGEN:" + ",".join(r["code"] for r in g["reasons"]))
    wc = len([k for k in (plan.get(i) or {}).get("text", "").split() if any(c.isalpha() for c in k)])
    wn = wpm(i, d2)
    if wc <= 9:
        if d2 / d1 < 0.75:
            bad.append("短句变短 x%.2f" % (d2 / d1))
        elif d2 / d1 > 1.40 and wn < 120:
            bad.append("短句变长且%.0fwpm" % wn)
    elif not (WPM_LO <= wn <= WPM_HI):
        bad.append("语速%.0fwpm" % wn)
    if pk >= 0.999:
        bad.append("削波")
    m_new = (NG.raw(new) or {}).get("nq_mos")
    m_old = (NG.raw(old) or {}).get("nq_mos")
    if m_new is not None and m_new < 1.5:
        bad.append("MOS崩%.2f" % m_new)
    go = old_gate.get(i) or {}
    if ((go.get("gates") or {}).get("speaker") == "PASS"
            and (g.get("gates") or {}).get("speaker") == "MANUAL"):
        bad.append("声纹PASS→MANUAL")
    print("%-8s %-6s %5.2f %5.2f %6.2f %7.0f %6s %s" % (
        i, g["verdict"], d1, d2, d2 / d1 if d1 else 0, wn,
        round(m_new, 2) if m_new is not None else "-", " ".join(bad) or "▶ 可回填"))
