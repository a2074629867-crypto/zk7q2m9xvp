import json, os, collections
base=r'G:/_setup/_emo_vote'
EMOS=['平静','紧张','激动反抗','委屈','兴奋','警惕']
for fn in ['r_ds1.jsonl','r_ds3.jsonl','r_b2.jsonl','r_d4.jsonl','r_adj.jsonl','_emo_final.jsonl']:
    p=os.path.join(base,fn)
    if not os.path.exists(p): print(fn,"MISSING"); continue
    n=0; keys=None; cnt=collections.Counter(); ids=set()
    for l in open(p,encoding='utf-8-sig'):
        l=l.strip()
        if not l: continue
        try: r=json.loads(l)
        except Exception as e: print(fn,"parse err",e); break
        n+=1
        if keys is None: keys=list(r.keys())
        e=r.get('emo') or r.get('final') or r.get('label')
        cnt[e]+=1; ids.add(r.get('id'))
    print(f"\n== {fn} == n={n} keys={keys} 唯一id={len(ids)}")
    print("  ",dict(cnt.most_common()))
