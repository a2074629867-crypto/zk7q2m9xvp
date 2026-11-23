import json, collections
rows=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
ids=[r.get('id') for r in rows]
c=collections.Counter(ids)
dup={k:v for k,v in c.items() if v>1}
print("总",len(rows),"唯一 id",len(c),"重复 id 数",len(dup))
for k,v in list(dup.items())[:20]: print("  重复:",k,v)
print("\n所有 c1_0014 记录：")
for i,r in enumerate(rows):
    if r.get('id')=='c1_0014':
        sp=r.get('spk') or {}
        print(f"  idx={i} verdict={r['verdict']} who={r['who']} emo={r['emo']} spk_role={sp.get('role')} z_target={sp.get('z_target')} dur={((r.get('tech') or {}).get('dur'))}")
print("\nplan 行数：")
p=[json.loads(l) for l in open(r'G:/_setup/_dlg_plan.jsonl',encoding='utf-8') if l.strip()]
print(" ",len(p),"唯一id",len(set(x.get('id') for x in p)))
pid=[x.get('id') for x in p]
pc=collections.Counter(pid)
print("  plan 重复:",{k:v for k,v in pc.items() if v>1})
