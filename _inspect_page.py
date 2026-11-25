# -*- coding: utf-8 -*-
import json, re
p = r"G:\_setup\_narr_ch2_listen.html"
s = open(p, encoding="utf-8").read()
m = re.search(r"const DATA = (\{.*?\});\n", s, re.S)
d = json.loads(m.group(1))
print("title", d.get("title"), "gen", d.get("generated"), "rows", len(d["rows"]))
r = [x for x in d["rows"] if x["id"] == "c2_0191"][0]
print("keys:", list(r.keys()))
for k, v in r.items():
    sv = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    print("  %-10s %s" % (k, sv[:400]))
print()
# 看 src/audio 前缀分布
pref = {}
for x in d["rows"]:
    for k, v in x.items():
        if isinstance(v, str) and v.lower().endswith(".wav"):
            pref.setdefault(k, {}).setdefault(v.rsplit("/", 1)[0], 0)
            pref[k][v.rsplit("/", 1)[0]] += 1
print("wav 字段前缀:", json.dumps(pref, ensure_ascii=False, indent=1)[:1200])
