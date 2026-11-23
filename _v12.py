import json, os
for b in ['B002','B003']:
    p=f'G:/_setup/_narr_new/rep/{b}.json'
    if not os.path.exists(p): print(b,"无报告"); continue
    d=json.load(open(p,encoding='utf-8'))
    rows=d.get('rows') or []
    added=sum(r.get('added') or 0 for r in rows)
    grew=[r for r in rows if (r.get('added') or 0)>0.01]
    print(f"{b}: 间隙 {len(rows)} 处，加长 {len(grew)} 处，累计补入 {added:.2f}s")
