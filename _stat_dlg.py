import json, collections
d=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
rows=d if isinstance(d,list) else (d.get('rows') or d.get('results') or [])
print("总条数", len(rows))
print("\n== verdict 分布 ==")
c=collections.Counter(r.get('verdict') for r in rows)
for k,v in c.most_common(): print(f"  {k:8s} {v:4d}  {v/len(rows)*100:5.1f}%")
print("\n== reasons 频次 ==")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []):
        rc[str(x).split(':')[0].split('(')[0]]+=1
for k,v in rc.most_common(30): print(f"  {k:24s} {v}")
print("\n== who x verdict ==")
whos=sorted(set(str(r.get('who')) for r in rows))
vers=['PASS','WARN','REGEN','MANUAL','FAIL']
print(f"{'who':10s}" + "".join(f"{v:>8s}" for v in vers) + "  合计")
for w in whos:
    sub=[r for r in rows if str(r.get('who'))==w]
    cc=collections.Counter(str(r.get('verdict')) for r in sub)
    print(f"{w:10s}" + "".join(f"{cc.get(v,0):>8d}" for v in vers) + f"{len(sub):>6d}")
print("\n== gates 各项 (各闸子判定) ==")
gc=collections.Counter()
for r in rows:
    g=r.get('gates') or {}
    for k,v in g.items():
        gc[(k,str(v))]+=1
for (k,v),n in sorted(gc.items()): print(f"  {k:8s} {v:12s} {n}")
