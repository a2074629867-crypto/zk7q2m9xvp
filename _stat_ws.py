import json, collections
d = json.load(open(r"G:/_setup/_gate_dlg.json", encoding="utf-8"))
rows = d if isinstance(d, list) else d["rows"]

ws = [r for r in rows if any((isinstance(x, dict) and x.get("code") == "wrong_speaker") for x in (r.get("reasons") or []))]
print("wrong_speaker n=", len(ws))
c_role = collections.Counter()
for r in ws:
    s = r.get("spk") or {}
    c_role[(r["who"], s.get("role_top"), s.get("emo"), s.get("emo_top"))] += 1
print("\n(who, role_top, plan_emo, emo_top) 频次:")
for k, v in c_role.most_common(30):
    print("  ", k, v)

print("\n逐条: id who plan_emo role_top/emas_top z_target z_other gap notes")
for r in ws:
    s = r.get("spk") or {}
    print("  %-9s %-8s %-6s top=%-8s/%-8s zt=%6.2f zo=%6.2f gap=%5.2f ref=%s" % (
        r["id"], r["who"], r.get("emo"),
        str(s.get("role_top")), str(s.get("emo_top")),
        float(s.get("z_target") or 0), float(s.get("z_other") or 0),
        float(s.get("role_gap") or 0), s.get("ref")))

# too_short
ts = [r for r in rows if any((isinstance(x, dict) and x.get("code") == "too_short") for x in (r.get("reasons") or []))]
print("\ntoo_short n=", len(ts))
for r in ts[:20]:
    print("  %-9s %-8s dur=%.2f %s" % (r["id"], r["who"], (r.get("tech") or {}).get("dur", 0), r.get("text", "")[:50]))

# role_ambiguous
ra = [r for r in rows if any((isinstance(x, dict) and x.get("code") == "role_ambiguous") for x in (r.get("reasons") or []))]
print("\nrole_ambiguous n=", len(ra), " who分布:", collections.Counter(r["who"] for r in ra))
