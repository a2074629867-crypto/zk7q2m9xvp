# -*- coding: utf-8 -*-
import json, re
s = open(r"G:\_setup\_narr_ch2_listen.html", encoding="utf-8").read()
d = json.loads(re.search(r"const DATA = (\{.*?\});\n", s, re.S).group(1))
from collections import Counter
c = Counter()
for x in d["rows"]:
    for k, v in (x.get("takes") or {}).items():
        c[(k, (v.get("src") or "").rsplit("/", 1)[0])] += 1
print(c)
r = [x for x in d["rows"] if x["id"] == "c2_0191"][0]
for k, v in r["takes"].items():
    print(k, "src=%s dur=%s fallback=%s" % (v.get("src"), v.get("dur"), v.get("fallback")),
          "keys=", [a for a in v if a not in ("env",)])
print("wpm_new/old:", r["wpm"], "| words", r["words"], "| pauses", r["pauses"], "| rate", r["rate"])
