import json, collections
d=json.load(open(r'G:/_setup/_narr_check/_narr_check.json',encoding='utf-8'))
rows=d if isinstance(d,list) else (d.get('rows') or d.get('results') or d.get('items') or [])
print("type",type(d),"keys",list(d.keys()) if isinstance(d,dict) else "", "len",len(rows))
if rows:
    print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:1500])
