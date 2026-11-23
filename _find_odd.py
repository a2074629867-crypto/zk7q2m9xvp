# -*- coding: utf-8 -*-
"""找出 tasks_v3t 里那个顶层是 list 的「非批文件」，并逐个确认 run_batch 能否吃下。"""
import json, os

root = "G:/_setup/_ann/tasks_v3t"
files = sorted(x for x in os.listdir(root) if x.endswith(".json"))
print("首 3:", files[:3])
print("末 3:", files[-3:])
print()
for b in files:
    o = json.load(open(os.path.join(root, b), encoding="utf-8"))
    if not isinstance(o, dict):
        print("!! 非 dict 批次: %s  type=%s  len=%d" % (b, type(o).__name__, len(o)))
        print("   样例:", json.dumps(o[:2], ensure_ascii=False)[:300])
    else:
        miss = [k for k in ("prompt", "items") if k not in o]
        if miss:
            print("!! 缺键 %s : %s" % (miss, b))
