import json, collections, os, glob

# 1) pause_plan
rows=[json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()]
print('plan rows', len(rows), 'total dur %.2f'%sum(r['dur'] for r in rows))
c=collections.Counter((r.get('tier'), r.get('dur')) for r in rows)
for k,v in sorted(c.items(), key=lambda x:-x[1]): print('  tier=%-10s dur=%-6s n=%d'%(k[0],k[1],v))
src=collections.Counter(r.get('src') for r in rows)
print('  src', dict(src))
print('  out-of-band:', sum(v for (t,d),v in c.items() if t not in ('inner','bound','clause')))

# 2) ann batches
for m in ('ds','hy4'):
    fs=sorted(glob.glob(f'_ann/out_full/narr/{m}/batch_*.json'))
    n=0; sids=set(); sl=0
    for f in fs:
        d=json.load(open(f,encoding='utf-8'))
        items = d if isinstance(d,list) else d.get('items') or d.get('results') or []
        for it in items:
            sids.add(it.get('sid') or it.get('id'))
            sl += len(it.get('slots') or it.get('pauses') or [])
    print(f'{m}: files={len(fs)} sentences={len(sids)} slots={sl}')

# 3) sample one batch
f=sorted(glob.glob('_ann/out_full/narr/ds/batch_*.json'))[0]
d=json.load(open(f,encoding='utf-8'))
print('sample keys', (list(d)[:5] if isinstance(d,dict) else type(d)))
print(json.dumps(d if isinstance(d,list) else d, ensure_ascii=False)[:800])
