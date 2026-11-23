import json, collections
p=json.load(open(r'G:/_setup/_narr_plan_v3.json',encoding='utf-8'))
bs=p['blocks']; base=p.get('base_rate',0.8)
blocks={b['bid']:b for b in json.load(open(r'G:/_setup/_narr_blocks.json',encoding='utf-8'))}
print("块数",len(bs),"base",base)
print("\nrate 分布:",dict(sorted(collections.Counter(b['rate'] for b in bs).items())))
print("\n减速块（rate<%.2f）："%base)
for b in bs:
    if b['rate']<base-1e-9:
        print(f"  {b['bid']} {b['words']:3d}词 rate={b['rate']:.2f}  {b.get('why','')[:50]}")
bych=collections.OrderedDict()
for b in bs: bych.setdefault(b.get('chapter'),[]).append(b)
print("\n== 按章校验 ==")
ok=True
for ch,arr in bych.items():
    tot=sum(blocks[x['bid']]['words'] for x in arr)
    slow=sum(blocks[x['bid']]['words'] for x in arr if x['rate']<base-1e-9)
    ne=sum(1 for x in arr if x['rate']<=0.72+1e-9)
    mx=0; pair=''
    for k in range(len(arr)-1):
        d=abs(arr[k]['rate']-arr[k+1]['rate'])
        if d>mx: mx=d; pair=f"{arr[k]['bid']}->{arr[k+1]['bid']}"
    cov=slow/tot*100
    f=[]
    if cov>20+1e-9: f.append('覆盖超20%'); ok=False
    if ne>1: f.append(f'≤0.72有{ne}段'); ok=False
    if mx>0.06+1e-9: f.append(f'相邻跳{mx:.2f}@{pair}'); ok=False
    print(f"  {ch:14s} {len(arr):2d}块 {tot:4d}词 减速{cov:5.1f}% 极值{ne} 最大跳{mx:.2f} [{'FAIL '+ ' / '.join(f) if f else 'OK'}]")
print("\n总:", "PASS" if ok else "FAIL")
