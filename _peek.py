import json, collections
d=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
rows=d if isinstance(d,list) else (d.get('rows') or d.get('results') or [])
print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:1800])
print("\n---- 一条 REGEN ----")
for r in rows:
    if str(r.get('verdict'))=='REGEN':
        print(json.dumps(r, ensure_ascii=False, indent=2)[:1800]); break
