import json, os, statistics
for b in ['B000','B001','B002']:
    p=f'G:/_setup/_narr_new/rep/{b}.json'
    if not os.path.exists(p): print(b,"无报告"); continue
    d=json.load(open(p,encoding='utf-8'))
    rows=d.get('rows') or []
    added=sum(r.get('added') or 0 for r in rows)
    grew=[r for r in rows if (r.get('added') or 0)>0.01]
    print(f"{b}: 间隙 {len(rows)} 处, 实际加长 {len(grew)} 处, 累计补入 {added:.2f}s")
    print(f"     目标时长分布: {sorted(set(round(r.get('target') or 0,2) for r in rows))}")
    print(f"     原时长 min={min((r.get('cur') or 0) for r in rows):.2f} 中位={statistics.median([(r.get('cur') or 0) for r in rows]):.2f} max={max((r.get('cur') or 0) for r in rows):.2f}")
