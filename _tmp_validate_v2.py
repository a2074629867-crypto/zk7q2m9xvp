import json, collections
rows=[json.loads(l) for l in open('_pause_plan_v2.jsonl',encoding='utf-8') if l.strip()]
# 阶梯第1条：句末标点必须 clause
END={'.','?','!','\u2026'}
bad=[r for r in rows if r['punct'] in END and r['kind']!='clause']
print('句末标点但未判 clause:', len(bad))
for r in bad: print('   %-12s punct=%r kind=%s  why=%s'%(r['bid'],r['punct'],r['kind'],r['why'][:50]))
print()
c=collections.Counter((r['punct'],r['kind']) for r in rows)
print('punct × kind:')
for (p,k),v in sorted(c.items(), key=lambda x:(str(x[0][0]),x[0][1])): print('   %-6r %-7s %d'%(p,k,v))
print()
print('秒数取值集合:', sorted({r['dur'] for r in rows}))
print('缺 why 的处数:', sum(1 for r in rows if not r['why']))
print('缺 k/punct 的处数:', sum(1 for r in rows if r['k'] is None or r['punct'] is None))
