import json, collections
rows=json.load(open(r'G:/_setup/_gate_dlg_v3.json',encoding='utf-8'))
N=len(rows)
print("== 全量 239 条：新情绪档（四模型投票）+ 判据修复前 ==")
for k,v in collections.Counter(r['verdict'] for r in rows).most_common():
    print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []): rc[x.get('code')]+=1
print("\n== reason ==")
for k,v in rc.most_common(): print(f"  {k:22s} {v}")
print("\n== 按情绪档 ==")
print(f"{'emo':10s}{'PASS':>6s}{'MANUAL':>8s}{'REGEN':>7s}{'合计':>6s}{'PASS率':>8s}")
for e in sorted(set(r.get('emo') for r in rows)):
    sub=[r for r in rows if r.get('emo')==e]
    c=collections.Counter(r['verdict'] for r in sub); n=len(sub)
    print(f"{e:10s}{c.get('PASS',0):>6d}{c.get('MANUAL',0):>8d}{c.get('REGEN',0):>7d}{n:>6d}{c.get('PASS',0)/n*100:>7.0f}%")
print("\n== 与旧情绪档（_gate_dlg_v2）对比 ==")
old={r['id']:r for r in json.load(open(r'G:/_setup/_gate_dlg_v2.json',encoding='utf-8'))}
mig=collections.Counter()
for r in rows:
    o=old.get(r['id'])
    if o: mig[(o['verdict'],r['verdict'])]+=1
for k,v in sorted(mig.items(), key=lambda x:-x[1]): print(f"  {k[0]:7s} → {k[1]:7s}  {v}")
