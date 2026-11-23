import json, statistics
rows=json.load(open(r'G:/_setup/_narr_check2/_narr_check.json',encoding='utf-8'))
sp=[(r['unit'],r['energy_span'],r['dur']) for r in rows if r.get('energy_span') is not None and (r.get('dur') or 0)>=2.5]
print("可测 span 条数（dur>=2.5s）:",len(sp))
vals=sorted(x[1] for x in sp)
print(f"  实测 p10={vals[int(.1*len(vals))]:.1f} p50={statistics.median(vals):.1f} p90={vals[int(.9*len(vals))]:.1f}")
for name,lo,hi in [("历史带(_rhythm_bands) narr",8.9,22.55),("真人切片",29.2,45.0),("Wonder 产物",10.2,25.5)]:
    low=sum(1 for v in vals if v<lo); high=sum(1 for v in vals if v>hi); ok=len(vals)-low-high
    print(f"  {name:28s} 带[{lo},{hi}]  LOW={low:4d}({low/len(vals)*100:4.1f}%) OK={ok:4d} HIGH={high}")
print("\n== dur<2.5s 不可测 ==")
print("  ", sum(1 for r in rows if (r.get('dur') or 0)<2.5))
