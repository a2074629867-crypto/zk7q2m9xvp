import json, collections, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = json.load(open(r"G:/_setup/_emo_refs_all.json", encoding="utf-8"))
for role, v in d.items():
    print("=" * 60)
    print("ROLE:", role, " type:", type(v).__name__, " n:", len(v))
    if isinstance(v, dict):
        for emo, lst in v.items():
            n = len(lst) if hasattr(lst, "__len__") else 1
            sample = lst[0] if isinstance(lst, list) and lst else lst
            print("   %-10s n=%-3d  %s" % (emo, n, json.dumps(sample, ensure_ascii=False)[:160]))
