import json, collections
rows=json.load(open(r'G:/_setup/_gate_regen.json',encoding='utf-8'))
N=len(rows)
print("== 重生成产物 %d 条 =="%N)
for k,v in collections.Counter(r['verdict'] for r in rows).most_common():
    print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
print("\n== reason ==")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []): rc[x.get('code')]+=1
for k,v in rc.most_common(): print(f"  {k:22s} {v}")
print("\n== 各闸 ==")
for g in ['tech','speaker','emotion']:
    print(f"  {g:9s}", dict(collections.Counter((r.get('gates') or {}).get(g) for r in rows)))
print("\n== 按情绪档看结果 ==")
emos=sorted(set(r.get('emo') for r in rows))
print(f"{'emo':10s}{'PASS':>7s}{'MANUAL':>8s}{'REGEN':>7s}{'合计':>7s}")
for e in emos:
    sub=[r for r in rows if r.get('emo')==e]
    cc=collections.Counter(r['verdict'] for r in sub)
    print(f"{e:10s}{cc.get('PASS',0):>7d}{cc.get('MANUAL',0):>8d}{cc.get('REGEN',0):>7d}{len(sub):>7d}")
print("\n== 与重生成前的旧判定对比（同一 id）==")
old={r['id']:r for r in json.load(open(r'G:/_setup/_gate_dlg_v2.json',encoding='utf-8'))}
mig=collections.Counter()
for r in rows:
    o=old.get(r['id'])
    if o: mig[(o['verdict'],r['verdict'])]+=1
for k,v in mig.most_common(): print(f"  {k[0]:7s} → {k[1]:7s}  {v}")
