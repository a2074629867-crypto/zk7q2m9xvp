import json, collections
d = json.load(open(r"G:/_setup/_gate_dlg.json", encoding="utf-8"))
rows = d if isinstance(d, list) else d["rows"]
print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:3000])
print("=" * 60)
codes = collections.Counter()
for r in rows:
    for x in (r.get("reasons") or []):
        if isinstance(x, dict):
            codes[x.get("code")] += 1
        else:
            codes[str(x)] += 1
print("CODES:", codes.most_common(40))
print("=" * 60)
# gate-level
gkeys = collections.Counter()
for r in rows:
    g = r.get("gates") or {}
    for k, v in g.items():
        gkeys[(k, str(v))] += 1
for k, v in gkeys.most_common(40):
    print(k, v)
