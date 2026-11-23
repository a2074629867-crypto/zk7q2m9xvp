# -*- coding: utf-8 -*-
"""正控：同一种「余弦到位度」口径，在 Expresso 真人内部能分对多少。
留一折：锚点=训练折均值，测试折逐条归类。真人能做对 → 口径可行，生成失败是域问题；
真人自己也做不对 → 这个口径的上限就在这里（与 SES-Judge 的 Spearman 0.53 一致）。"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
EXPR = {"happy": {"happy", "laughing"}, "sad": {"sad"}, "neutral": {"default"}}
emb_json = json.load(open(os.path.join(OUT, "e2v_emb.json"), encoding="utf-8"))
meta = {r["path"]: dict(style=r["style"]) for r in
        map(json.loads, open(os.path.join(OUT, "real_vox_dim.jsonl"), encoding="utf-8"))}
def cls_of(st):
    for c, ss in EXPR.items():
        if st in ss: return c
    return None
def cos(a,b):
    return float(a@b/(np.linalg.norm(a)*np.linalg.norm(b)+1e-12))
items=[]
for p,m in meta.items():
    c=cls_of(m["style"])
    if c and p in emb_json:
        items.append((p,c,np.array(emb_json[p],dtype=np.float32)))
print("真人三分类可用 %d 条：%s"%(len(items),
      {c:sum(1 for x in items if x[1]==c) for c in ["happy","sad","neutral"]}))
rng=np.random.default_rng(0)
idx=np.array([i for i in range(len(items))]); rng.shuffle(idx)
folds=np.array_split(idx,5)
y=[];p=[]
for f in folds:
    test=[items[i] for i in f]; train=[items[i] for i in idx if i not in set(f.tolist())]
    proto={}
    for c in ["happy","sad","neutral"]:
        vs=[it[2] for it in train if it[1]==c]
        proto[c]=np.mean(np.stack(vs),0)
    for path,c,v in test:
        sc={k:cos(v,proto[k]) for k in proto}
        y.append(c); p.append(max(sc,key=sc.get))
acc=np.mean([a==b for a,b in zip(y,p)])
base=max(y.count(c) for c in set(y))/len(y)
print("5 折交叉：accuracy = %.3f   类别基线 = %.3f"%(acc,base))
labels=["happy","sad","neutral"]
print("  %-9s %s"%("","".join("%-9s"%c for c in labels)))
for c in labels:
    row=[sum(1 for a,b in zip(y,p) if a==c and b==d) for d in labels]
    print("  %-9s %s  n=%d"%(c,"".join("%-9d"%v for v in row),sum(row)))
# 同期再用分类 top-1
e2={r["path"]:r["score"] for r in map(json.loads,open(os.path.join(OUT,"real_e2v.jsonl"),encoding="utf-8")) if r.get("score")}
CN={"开心/happy":"happy","难过/sad":"sad","中立/neutral":"neutral"}
y2=[];p2=[]
for p_,c,_ in items:
    s=e2.get(p_)
    if s: y2.append(c); p2.append(CN.get(s["_top"],s["_top"]))
print("同一批：分类 top-1 accuracy = %.3f  n=%d"%(np.mean([a==b for a,b in zip(y2,p2)]),len(y2)))
