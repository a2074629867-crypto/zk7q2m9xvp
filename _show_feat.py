# -*- coding: utf-8 -*-
import json, sys
p = sys.argv[1]
n = 0
for ln in open(p, encoding="utf-8"):
    r = json.loads(ln)
    print("==", r["id"], "dur", r["dur"], "med", r["med"], "nw", r["nw"])
    print("   text:", r["text"][:110])
    for w in r["words"][:14]:
        print("   %-12s %-5s %-8s head=%-10s p50=%-7s p95=%s"
              % (w["w"], w["pos"], w["dep"], w["head"], w["p50"], w["p95"]))
    n += 1
    if n >= 2:
        break
