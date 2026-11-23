import json, glob, collections
plan=[json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()]
ann={}
for f in glob.glob('_ann/out_full/narr/ds/batch_*.json'):
    for it in json.load(open(f,encoding='utf-8'))['items']:
        ann[it['sid']]=it
psid={r['sid'] for r in plan}
print('plan sids %d  ann sids %d  plan∩ann %d  plan-only %d  ann-only %d'%(
    len(psid), len(ann), len(psid&set(ann)), len(psid-set(ann)), len(set(ann)-psid)))
pbid={r['bid'] for r in plan}
abid={p['bid'] for it in ann.values() for p in it['pause']}
print('plan bids %d  ann bids %d  inter %d  plan-only %d  ann-only %d'%(
    len(pbid), len(abid), len(pbid&abid), len(pbid-abid), len(abid-pbid)))
print('plan-only bid 样本:', sorted(pbid-abid)[:10])
print('ann-only bid 样本:', sorted(abid-pbid)[:10])
# 逐句：标注槽数 vs 标点数
short=[(s,len(ann[s]['pause']),sum(1 for r in plan if r['sid']==s)) for s in sorted(psid&set(ann))]
d=[x for x in short if x[1]!=x[2]]
print('句内槽数与标点数不一致的句:', len(d), d[:8])
# ann 句里 plan 没有的
print('ann-only sids:', sorted(set(ann)-psid)[:10])
