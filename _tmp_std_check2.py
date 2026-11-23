import json, collections, glob
rows=[json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()]
t=collections.Counter((r['punct'], r['tier'], r['dur']) for r in rows)
print('punct  tier        dur    n')
for (p,tier,d),v in sorted(t.items(), key=lambda x:(x[0][0],-x[1])):
    print('%-6r %-10s %-6s %d'%(p,tier,d,v))
print()
print('有多少处是 clause 值 1.695 :', sum(1 for r in rows if abs(r['dur']-1.695)<0.01))
print('句末标点处数:', sum(1 for r in rows if r['punct'] in ('.','?','!','\u2026','.\u2019','!\u2019','?\u2019')))
print('逗号处数:', sum(1 for r in rows if r['punct']==','))
print('其他 punct:', collections.Counter(r['punct'] for r in rows if r['punct']!=','))

# 标注
for m in ('ds','hy4'):
    fs=sorted(glob.glob(f'_ann/out_full/narr/{m}/batch_*.json'))
    sids=[]; slots=0; tierc=collections.Counter()
    for f in fs:
        d=json.load(open(f,encoding='utf-8'))
        for it in d['items']:
            sids.append(it['sid']); slots+=len(it['pause'])
            for p in it['pause']: tierc[p.get('tier')]+=1
    print(f'{m}: batches={len(fs)} sids={len(sids)} uniq={len(set(sids))} slots={slots} tiers={dict(tierc)}')
