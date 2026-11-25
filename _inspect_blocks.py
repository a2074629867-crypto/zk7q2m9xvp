# -*- coding: utf-8 -*-
import json
b = json.load(open(r"G:\_setup\_narr_blocks.json", encoding="utf-8"))
print(type(b).__name__, len(b))
print("keys:", list(b[0].keys()))
print(json.dumps(b[0], ensure_ascii=False)[:500])
ns = [len(x.get("ids") or x.get("sents") or []) for x in b]
print("每块句数: min %d / med %.1f / max %d / 合计 %d"
      % (min(ns), sorted(ns)[len(ns) // 2], max(ns), sum(ns)))
