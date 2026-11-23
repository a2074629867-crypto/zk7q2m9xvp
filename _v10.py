import json, collections
rows=[json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan_v2.jsonl',encoding='utf-8') if l.strip()]
print("plan_v2 条数",len(rows))
print("字段:",list(rows[0].keys()))
print("\n样例:")
print(json.dumps(rows[0],ensure_ascii=False)[:400])
print("\nvoice 分布:")
for k,v in collections.Counter(r.get('voice') for r in rows if r.get('speaker')!='narrator').most_common(): print(f"  {k}: {v}")
print("\nemo 分布:")
for k,v in collections.Counter(r.get('emo') for r in rows if r.get('speaker')!='narrator').most_common(): print(f"  {k}: {v}")
