# -*- coding: utf-8 -*-
"""彻底摸清 tasks_v3 / tasks_v3t 的批文件形状（顶层 dict/list 混杂，别猜）。"""
import json, os
from collections import Counter

for d in ("tasks_v3", "tasks_v3t"):
    root = "G:/_setup/_ann/" + d
    files = sorted(x for x in os.listdir(root) if x.endswith(".json"))
    shapes = Counter()
    keysets = Counter()
    itemk = Counter()
    total_items = total_slots = 0
    for b in files:
        o = json.load(open(os.path.join(root, b), encoding="utf-8"))
        shapes[type(o).__name__] += 1
        items = o if isinstance(o, list) else (o.get("items") or [])
        if isinstance(o, dict):
            keysets[tuple(sorted(o.keys()))] += 1
        total_items += len(items)
        for it in items:
            if isinstance(it, dict):
                itemk[tuple(sorted(it.keys()))] += 1
                sl = it.get("slots")
                total_slots += len(sl) if isinstance(sl, list) else (1 if sl else 0)
    print("### %s  批=%d  顶层形状=%s  条目=%d  槽位≈%d" % (d, len(files), dict(shapes), total_items, total_slots))
    for k, v in keysets.items():
        print("    顶层 keys x%d: %s" % (v, k))
    for k, v in itemk.most_common(3):
        print("    item keys x%d: %s" % (v, k))
    print()
