import json, glob, re
ctx={}
for l in open('_pause_ctx.jsonl',encoding='utf-8'):
    r=json.loads(l); ctx[r['bid']]=r
plan={json.loads(l)['bid']: json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()}
ann={}
for f in glob.glob('_ann/out_full/narr/ds/batch_*.json'):
    for it in json.load(open(f,encoding='utf-8'))['items']:
        for p in it['pause']: ann[p['bid']]=p
plan_only=[b for b in plan if b not in ann]
ann_only=[b for b in ann if b not in plan]
for tag,lst in (('PLAN-ONLY(标注漏)',plan_only),('ANN-ONLY(表漏标点)',ann_only)):
    print('='*20, tag, len(lst))
    seen=set()
    for b in sorted(lst):
        c=ctx.get(b)
        sid=b.split('#')[0]
        if sid not in seen:
            seen.add(sid); print('\n[%s] %s'%(sid, c['sent'] if c else 'NO CTX'))
        print('   %-12s k=%s punct=%r  L=%r | R=%r  plan=%s ann=%s'%(
            b, c['k'] if c else '?', c['punct'] if c else '?',
            (c['left'][-38:] if c else ''), (c['right'][:38] if c else ''),
            plan.get(b,{}).get('tier'), ann.get(b,{}).get('tier')))
# 标点计数核对
print('\n=== 标点计数核对（按 sent 数标点 vs plan 槽数）===')
from collections import defaultdict
cnt=defaultdict(int)
for b in plan: cnt[b.split('#')[0]]+=1
bad=[]
for sid,c in ctx.items():
    pass
for sid in sorted({b.split('#')[0] for b in list(plan)+list(ann)}):
    c=[v for v in ctx.values() if v['sid']==sid]
    if not c: continue
    s=c[0]['sent']
    n=len(re.findall(r'[,;:!?\u2013]|\.(?!\.)', s))
    if n!=max(cnt.get(sid,0), sum(1 for b in ann if b.split('#')[0]==sid)):
        bad.append((sid,n,cnt.get(sid,0),sum(1 for b in ann if b.split('#')[0]==sid),s[:70]))
print('计数不一致句数:',len(bad))
for x in bad[:12]: print('  ',x)
