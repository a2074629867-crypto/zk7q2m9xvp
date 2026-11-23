import json, random
v1={json.loads(l)['bid']:json.loads(l) for l in open('_pause_plan.jsonl',encoding='utf-8') if l.strip()}
ctx={}
for l in open('_pause_ctx.jsonl',encoding='utf-8'):
    r=json.loads(l); ctx[r['bid']]=r
v2=[json.loads(l) for l in open('_pause_plan_v2.jsonl',encoding='utf-8') if l.strip()]
pool=[r for r in v2 if r['bid'] in v1 and v1[r['bid']]['tier']=='mid' and r['kind']=='inner']
random.seed(7)
for r in random.sample(pool,5):
    c=ctx.get(r['bid'],{})
    print('[%s] %s'%(r['bid'], (c.get('sent') or '')[:100]))
    print('   L=%r  R=%r'%((c.get('left') or '')[-40:], (c.get('right') or '')[:45]))
    print('   why=%s\n'%r['why'][:80])
