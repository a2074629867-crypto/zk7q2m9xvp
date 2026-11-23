# -*- coding: utf-8 -*-
"""_drift_refresh.py —— 只重算「时长与缓存不一致」的条目，输出到新文件（不改原缓存）。"""
import json, os, sys
sys.path.insert(0, "G:/_setup")
import soundfile as sf
import mt_seg_drift as D

CACHE = "G:/_setup/_drift_cache.json"
AUD = "G:/_setup/_audio_ch123/out"
OUT = "G:/_setup/_drift_refresh_v29.json"

d = json.load(open(CACHE, encoding="utf-8"))
stale = []
for x in d:
    k = os.path.basename(x["file"])[:-4]
    p = os.path.join(AUD, k + ".wav")
    if not os.path.exists(p):
        continue
    dur = sf.info(p).duration
    if abs(dur - x["dur"]) > 0.05:
        stale.append(k)

rows, changed = [], []
for i, k in enumerate(sorted(stale), 1):
    p = os.path.join(AUD, k + ".wav")
    try:
        r = D.one(p)
    except Exception as e:
        rows.append({"k": k, "error": str(e)})
        continue
    old = next(x["verdict"] for x in d if os.path.basename(x["file"])[:-4] == k)
    rows.append({"k": k, "old": old, "new": r["verdict"], "dur": r["dur"],
                 "n_ev": len(r.get("events") or [])})
    if old != r["verdict"]:
        changed.append((k, old, r["verdict"]))
    if i % 20 == 0:
        print("  %d/%d" % (i, len(stale)), flush=True)

json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
import collections
print("重算 %d 条 -> %s" % (len(rows), OUT))
print("新判决分布:", dict(collections.Counter(r.get("new") for r in rows)))
print("变了的 %d 条:" % len(changed))
for c in changed:
    print("   %-8s %-12s -> %s" % c)
