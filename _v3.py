import json, collections
rows=[json.loads(l) for l in open(r'G:/_setup/_emo_vote/_emo_final.jsonl',encoding='utf-8-sig') if l.strip()]
print("n=",len(rows),"keys=",list(rows[0].keys()))
print("\n样例：")
for r in rows[:4]: print(" ",json.dumps(r,ensure_ascii=False))
print("\n== src 分布（决策来源）==")
for k,v in collections.Counter(r.get('src') for r in rows).most_common(): print(f"  {k}: {v}")
print("\n== votes 结构 ==")
vs=collections.Counter(str(r.get('votes'))[:80] for r in rows)
for k,v in vs.most_common(6): print(f"  {v:4d}  {k}")
