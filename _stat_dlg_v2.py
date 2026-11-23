import json, collections, statistics
rows=json.load(open(r'G:/_setup/_gate_dlg_v2.json',encoding='utf-8'))
N=len(rows)
print("== 新判据（centroid 模式）对白结果 %d 条 =="%N)
for k,v in collections.Counter(r.get('verdict') for r in rows).most_common():
    print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
print("\n== 与旧结果对比 ==")
old={json.loads(l)['id']:json.loads(l) for l in open(r'G:/_setup/_gate_dlg.json',encoding='utf-8') if l.strip()}
chg=collections.Counter()
for r in rows:
    o=old.get(r['id'])
    if o: chg[(o['verdict'],r['verdict'])]+=1
for k,v in chg.most_common(): print(f"  旧{k[0]:7s} → 新{k[1]:7s}  {v}")
print("\n== reason 频次 ==")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []): rc[x.get('code')]+=1
for k,v in rc.most_common(): print(f"  {k:20s} {v}")
print("\n== who x verdict ==")
vers=['PASS','MANUAL','REGEN']
print(f"{'who':10s}"+"".join(f"{v:>8s}" for v in vers))
for w in sorted(set(str(r.get('who')) for r in rows)):
    sub=[r for r in rows if str(r.get('who'))==w]
    cc=collections.Counter(str(r.get('verdict')) for r in sub)
    print(f"{w:10s}"+"".join(f"{cc.get(v,0):>8d}" for v in vers)+f"{len(sub):>6d}")
print("\n== 各闸 ==")
for gate in ['tech','speaker','emotion']:
    cc=collections.Counter((r.get('gates') or {}).get(gate) for r in rows)
    print(f"  {gate:9s}", dict(cc))
