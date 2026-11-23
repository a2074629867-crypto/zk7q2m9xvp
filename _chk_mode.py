import json
rows=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
n=len(rows)
cen=sum(1 for r in rows if (r.get('spk') or {}).get('cen_gap') is not None)
zt=sum(1 for r in rows if (r.get('spk') or {}).get('z_target') is not None)
print("总",n,"cen_gap 有值",cen,"z_target 有值",zt)
print("\n样例 spk 键：")
for r in rows[:3]:
    print(" ", r['id'], list((r.get('spk') or {}).keys()))
print("\nc1_0014:", json.dumps(rows[13].get('spk'),ensure_ascii=False))
