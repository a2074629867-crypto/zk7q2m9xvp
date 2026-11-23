import json, collections
rows=json.load(open(r'G:/_setup/_gate_dlg_v2.json',encoding='utf-8'))
old_raw=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
old={r['id']:r for r in (old_raw if isinstance(old_raw,list) else old_raw.get('rows',[]))}
N=len(rows)
print("新:",dict(collections.Counter(r['verdict'] for r in rows)))
print("旧:",dict(collections.Counter(r['verdict'] for r in old.values())))
chg=collections.Counter()
for r in rows:
    o=old.get(r['id'])
    if o: chg[(o['verdict'],r['verdict'])]+=1
print("\n== 迁移 ==")
for k,v in chg.most_common(): print(f"  {k[0]:7s} → {k[1]:7s}  {v}")
print("\n== 新 reason ==")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []): rc[x.get('code')]+=1
for k,v in rc.most_common(): print(f"  {k:22s} {v}")
print("\n== 新 note ==")
nc=collections.Counter()
for r in rows:
    for x in (r.get('notes') or []): nc[x.get('code')]+=1
for k,v in nc.most_common(): print(f"  {k:22s} {v}")
print("\n== 11 条 REGEN 明细 ==")
for r in rows:
    if r['verdict']=='REGEN':
        sp=r.get('spk') or {}
        print(f"  {r['id']:10s} {r['who']:8s} 判成={sp.get('cen_top')} gap={sp.get('cen_gap')}  原因={[x['code'] for x in r.get('reasons') or []]}")
