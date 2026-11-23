import json, collections, statistics
rows=json.load(open(r'G:/_setup/_narr_check2/_narr_check.json',encoding='utf-8'))
blocks=json.load(open(r'G:/_setup/_narr_blocks.json',encoding='utf-8'))
fix={r['unit'] for r in rows if r.get('verdict')=='FIX'}
print("FIX 总数",len(fix))
per=collections.OrderedDict()
for b in blocks:
    n=sum(1 for i in b['ids'] if i in fix)
    per[b['bid']]=n
tot=sum(per.values())
print("覆盖块数:",sum(1 for v in per.values() if v>0),"/",len(per))
# 按 FIX 密度排序
top=sorted(per.items(), key=lambda x:-x[1])
print("\nFIX 最多的 20 块：")
for bid,n in top[:20]:
    if n==0: break
    b=[x for x in blocks if x['bid']==bid][0]
    print(f"  {bid} {b['words']:3d}词  FIX {n:2d}/{b['n']:2d}")
cum=0
print("\n累计覆盖分析：")
for k,(bid,n) in enumerate(top):
    if n==0: break
    cum+=n
    if k+1 in (10,15,20,25,30,40):
        print(f"  重生成前 {k+1} 块 → 覆盖 {cum}/{tot} = {cum/tot*100:.0f}% 的 FIX")
print("\nFIX 分布直方图：")
h=collections.Counter(per.values())
for k in sorted(h): print(f"  每块 {k} 条 FIX: {h[k]} 块")
