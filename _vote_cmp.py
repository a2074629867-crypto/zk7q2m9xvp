import json, collections, itertools
def load(p):
    d={}
    for l in open(p,encoding='utf-8-sig'):
        l=l.strip()
        if not l: continue
        r=json.loads(l); d[r['id']]=r
    return d
A=load(r'G:/_setup/_emo_vote/r_ds1.jsonl')
C=load(r'G:/_setup/_emo_vote/r_ds3b.jsonl')
print("A",len(A),"C",len(C),"共同 id",len(set(A)&set(C)))
EMOS=['平静','紧张','激动反抗','委屈','兴奋','警惕']
print("\n== 逐条一致率 ==")
same=sum(1 for k in A if k in C and A[k]['emo']==C[k]['emo'])
print(f"  emo 完全相同: {same}/{len(A)} = {same/len(A)*100:.1f}%")
print("\n== 混淆矩阵 (行=A, 列=C) ==")
print(f"{'':10s}"+"".join(f"{e:>8s}" for e in EMOS))
for a in EMOS:
    row=[sum(1 for k in A if k in C and A[k]['emo']==a and C[k]['emo']==c) for c in EMOS]
    if sum(row): print(f"{a:10s}"+"".join(f"{v:>8d}" for v in row)+f"{sum(row):>7d}")
print("\n== 分歧明细（前 30，按分歧维度）==")
dis=[k for k in A if k in C and A[k]['emo']!=C[k]['emo']]
print(" 分歧总数",len(dis))
cc=collections.Counter((A[k]['emo'],C[k]['emo']) for k in dis)
for (a,c),n in cc.most_common(10): print(f"   A={a:8s} vs C={c:8s}  {n}")
