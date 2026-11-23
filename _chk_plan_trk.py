# -*- coding: utf-8 -*-
"""验 merge 的轨道判定：plan jsonl 里的 speaker 是否真能让 716 条旁白落到 narr 尺度。"""
import json, os, glob
from collections import Counter

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
print("plan 存在:", os.path.exists(PLAN))
spk = {}
for ln in open(PLAN, encoding="utf-8"):
    ln = ln.strip()
    if ln:
        r = json.loads(ln)
        spk[r["id"]] = r.get("speaker") or ""
print("plan 条数:", len(spk), " speaker 分布:", Counter(spk.values()).most_common(8))

# 从 tasks_v3t 里取旁白 sid
sids = set()
for fp in glob.glob("G:/_setup/_ann/tasks_v3t/batch_*.json"):
    o = json.load(open(fp, encoding="utf-8"))
    for it in (o.get("items") or []):
        sids.add(it.get("sid"))
print("tasks 旁白 sid 去重:", len(sids))

miss = sorted(s for s in sids if s not in spk)
print("plan 里查不到 sid 的:", len(miss), miss[:5])
trk = Counter()
for s in sids:
    who = spk.get(s, "")
    trk["narr" if who == "narrator" else "dlg"] += 1
print("按 track_of_speaker 判定结果:", dict(trk))
