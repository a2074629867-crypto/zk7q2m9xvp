import json, collections
rows=json.load(open(r'G:/_setup/_gate_regen.json',encoding='utf-8'))
# 从 spk.ref 或 plan 取实际参考档
plan={json.loads(l)['id']:json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan_v2.jsonl',encoding='utf-8') if l.strip()}
print(f"{'实际参考档':24s}{'PASS':>6s}{'MANUAL':>8s}{'REGEN':>7s}{'合计':>6s}{'PASS率':>8s}")
by=collections.defaultdict(collections.Counter)
for r in rows:
    p=plan.get(r['id']) or {}
    v=p.get('voice') or '?'
    by[v][r['verdict']]+=1
for v,c in sorted(by.items(), key=lambda x:-sum(x[1].values())):
    n=sum(c.values())
    print(f"{v:24s}{c.get('PASS',0):>6d}{c.get('MANUAL',0):>8d}{c.get('REGEN',0):>7d}{n:>6d}{c.get('PASS',0)/n*100:>7.0f}%")
print("\n== Thomas 激动反抗 的 intensity 分布 ==")
fin={json.loads(l)['id']:json.loads(l) for l in open(r'G:/_setup/_emo_vote/_emo_final.jsonl',encoding='utf-8') if l.strip()}
th=[(i,f) for i,f in fin.items() if f.get('who')=='Thomas' and f.get('emo')=='激动反抗']
print(" 条数",len(th),"intensity:",dict(collections.Counter(f.get('intensity') for i,f in th)))
print("\n== 重生成产物中 Thomas 激动反抗 按 intensity 看 PASS ==")
g=collections.defaultdict(collections.Counter)
for r in rows:
    f=fin.get(r['id'])
    if not f or f.get('who')!='Thomas' or f.get('emo')!='激动反抗': continue
    g[f.get('intensity')][r['verdict']]+=1
for k in sorted(g):
    c=g[k]; n=sum(c.values())
    print(f"  intensity {k}: PASS {c.get('PASS',0)}/{n} = {c.get('PASS',0)/n*100:.0f}%")
