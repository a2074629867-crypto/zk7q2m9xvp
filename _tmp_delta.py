import json, collections
v1={json.loads(l)['bid']:json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()}
v2=[json.loads(l) for l in open('_pause_plan_v2.jsonl',encoding='utf-8') if l.strip()]
agg=collections.defaultdict(lambda:[0,0.0])
for r in v2:
    o=v1.get(r['bid'])
    if not o: continue
    k=(o['tier'], o['dur'], r['kind'])
    agg[k][0]+=1; agg[k][1]+=r['dur']-o['dur']
print('v1档 → v2档   处数   总Δs   均Δs')
for k,(n,d) in sorted(agg.items(), key=lambda x:-abs(x[1][1])):
    print('  %-9s %.2f → %-7s  %4d  %+8.2f  %+.3f'%(k[0],k[1],k[2],n,d,d/n))
print('\n合计 Δ %.2f'%sum(d for n,d in agg.values()))
longer=sum(1 for r in v2 if r['bid'] in v1 and r['dur']>v1[r['bid']]['dur'])
shorter=sum(1 for r in v2 if r['bid'] in v1 and r['dur']<v1[r['bid']]['dur'])
same=sum(1 for r in v2 if r['bid'] in v1 and r['dur']==v1[r['bid']]['dur'])
print('变长 %d / 变短 %d / 不变 %d（共 %d 可比）'%(longer,shorter,same,longer+shorter+same))
