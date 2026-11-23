import json, collections
rows=[json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan.jsonl',encoding='utf-8') if l.strip()]
print("plan 总条",len(rows))
voices=collections.Counter(r.get('voice') for r in rows if r.get('speaker')!='narrator')
print("对白 voice 档位分布:")
for k,v in voices.most_common(): print(f"  {k}: {v}")
