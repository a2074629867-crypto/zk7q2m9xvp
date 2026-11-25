# -*- coding: utf-8 -*-
import json, os

ID = "c2_0191"
for p in [r"G:\_setup\_words.json", r"G:\_setup\_narr_blocks.json",
          r"G:\_setup\_wl_regen1123.json", r"G:\_setup\_wl_words.json"]:
    if not os.path.exists(p):
        print("MISS", p); continue
    o = json.load(open(p, encoding="utf-8"))
    print("==", os.path.basename(p), type(o).__name__, len(o))
    if isinstance(o, dict):
        v = o.get(ID)
        print("  keys sample:", list(o.keys())[:3])
        print("  v:", json.dumps(v, ensure_ascii=False)[:700] if v is not None else None)
    print()
