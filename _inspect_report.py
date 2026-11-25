# -*- coding: utf-8 -*-
import json
for p in [r"G:\_setup\_pause_norm_report.json", r"G:\_setup\_pause_regen1123_report.json"]:
    o = json.load(open(p, encoding="utf-8"))
    print("==", p, type(o), len(o))
    it = o[0]
    print("  item type", type(it))
    if isinstance(it, dict):
        print("  keys:", list(it.keys()))
        print("  sample:", json.dumps(it, ensure_ascii=False)[:600])
    # 找 c2_0191
    for k in (o if isinstance(o, list) else []):
        s = json.dumps(k, ensure_ascii=False)
        if "c2_0191" in s:
            print("  HIT:", s[:900])
            break
