# -*- coding: utf-8 -*-
"""_drift_heal.py —— 把「音频已变」的漂移缓存条目原地重算并写回（2026-11-14 14:4x）

与 `_drift_refresh.py` 的区别：那个只出摘要（_drift_refresh_v29.json，94 条 k/old/new），
不能直接当缓存用；本脚本重算后**保留完整结构**（windows/events/span）并写回
`_drift_cache.json`，这样 `gate_intra` 的 dur 断言才能通过、不用每次实时重算。

用法：G:/Python310/python.exe _drift_heal.py
"""
import sys, os, json, shutil
from datetime import datetime

sys.path.insert(0, r"G:/_setup")
os.chdir(r"G:/_setup")
import soundfile as sf
import mt_seg_drift as D

CACHE = "_drift_cache.json"
TOL = 0.05

old = json.load(open(CACHE, encoding="utf-8"))
print("缓存 %d 条" % len(old))

stale = []
for x in old:
    p = x["file"]
    try:
        ad = sf.info(p).duration
    except Exception:
        stale.append((x, None))
        continue
    if x.get("dur") is None or abs(float(x["dur"]) - ad) > TOL:
        stale.append((x, ad))

print("需要重算 %d 条" % len(stale))
if not stale:
    sys.exit(0)

bak = "_drift_cache.%s.bak.json" % datetime.now().strftime("%Y%m%d_%H%M")
shutil.copy(CACHE, bak)
print("旧缓存备份 -> %s" % bak)

changed = []
for i, (x, ad) in enumerate(stale, 1):
    sid = os.path.basename(x["file"])[:-4]
    try:
        r = D.one(x["file"])
    except Exception as e:
        print("  [FAIL] %s %s" % (sid, e))
        continue
    r["file"] = x["file"]
    ov, nv = x.get("verdict"), r.get("verdict")
    if ov != nv:
        changed.append((sid, ov, nv))
    old = [r if os.path.basename(o["file"])[:-4] == sid else o for o in old]
    if i % 20 == 0:
        print("  %d/%d" % (i, len(stale)), flush=True)

tmp = CACHE + ".tmp"
json.dump(old, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
os.replace(tmp, CACHE)
print("\n写回 %s（%d 条）" % (CACHE, len(old)))

print("\n判决变化 %d 条：" % len(changed))
for sid, ov, nv in changed:
    print("  %-10s %-14s -> %s" % (sid, ov, nv))
json.dump([dict(id=s, old=o, new=n) for s, o, n in changed],
          open("_drift_healed_changed.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("变化清单 -> _drift_healed_changed.json")
