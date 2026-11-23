# -*- coding: utf-8 -*-
"""查交付版里时长明显不合理的条目（模型多念了内容 / 只念了半个字）。"""
import io
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG

plan = CG.load_plan()
rep = json.load(io.open("_deliver_report.json", encoding="utf-8"))
al = {r["id"]: r for r in json.load(io.open("_align_deliver.json", encoding="utf-8"))}

base = {}
for role in {p.get("who") for p in plan.values() if p.get("who")}:
    try:
        base[role] = CG.baseline(plan, role)["med"]["wpm_voiced"]
    except Exception:
        base[role] = 270

rows = []
for rid, v in rep.items():
    p = plan.get(rid, {})
    nw = CG.spoken_words(p.get("text") or "")
    wpm = base.get(p.get("who") or "Charles", 270)
    exp = nw / wpm * 60.0
    d = v.get("dur")
    if d is None:
        import soundfile as sf
        d = sf.info(os.path.join("G:/_setup/_audio_ch123/out_deliver", rid + ".wav")).duration
        v["dur"] = round(d, 2)
    r = exp and d / exp
    if r and (r < 0.55 or r > 1.9):
        rows.append((round(r, 2), rid, round(v["dur"], 2), round(exp, 2), nw,
                     ((al.get(rid) or {}).get("w2v_text") or "")[:56]))
rows.sort(reverse=True)
print("时长异常 %d 条（ratio = 实际/期望；期望按同角色吐字中位语速推算）" % len(rows))
for r, rid, d, e, nw, hyp in rows:
    print("  %-9s %.2f×  实 %.2fs 期望 %.2fs  %2d词  %s" % (rid, r, d, e, nw, hyp))
