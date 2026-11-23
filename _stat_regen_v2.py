import json, collections
rows=json.load(open(r'G:/_setup/_gate_regen_v2.json',encoding='utf-8'))
N=len(rows)
print("== 修复判据后重跑 76 条 ==")
for k,v in collections.Counter(r['verdict'] for r in rows).most_common():
    print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
print("\n== reason ==")
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []): rc[x.get('code')]+=1
for k,v in rc.most_common(): print(f"  {k:22s} {v}")
print("\n== 修复前后对比 ==")
old={r['id']:r for r in json.load(open(r'G:/_setup/_gate_regen.json',encoding='utf-8'))}
mig=collections.Counter()
for r in rows:
    o=old.get(r['id'])
    if o: mig[(o['verdict'],r['verdict'])]+=1
for k,v in sorted(mig.items(), key=lambda x:-x[1]): print(f"  {k[0]:7s} → {k[1]:7s}  {v}")
