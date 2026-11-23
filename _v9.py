import json, collections
rows=[json.loads(l) for l in open(r'G:/_setup/_regen_v2.jsonl',encoding='utf-8') if l.strip()]
print("重生成日志 %d 条"%len(rows))
print("  ok:",sum(1 for r in rows if r.get('ok')),"fail:",sum(1 for r in rows if not r.get('ok')))
vc=collections.Counter(r.get('voice') for r in rows)
print("\n用的音色档:")
for k,v in vc.most_common(): print(f"  {k}: {v}")
d=[r['dur'] for r in rows if r.get('dur')]
if d: print("\n时长 min=%.1f 中位=%.1f max=%.1f 总=%.1f分"%(min(d),sorted(d)[len(d)//2],max(d),sum(d)/60))
t=[r['sec'] for r in rows if r.get('sec')]
if t: print("耗时 中位=%.0fs 总=%.1f分"%(sorted(t)[len(t)//2],sum(t)/60))
