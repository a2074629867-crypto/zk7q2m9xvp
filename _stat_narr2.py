import json, collections, statistics
rows=json.load(open(r'G:/_setup/_narr_check2/_narr_check.json',encoding='utf-8'))
N=len(rows)
print("== 重跑后 verdict（%d 条）=="%N)
for k,v in collections.Counter(r.get('verdict') for r in rows).most_common():
    print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
print("\n== cut_hard 应为 0 ==", sum(1 for r in rows if r.get('cut_hard')))
print("\n== energy_band ==")
for k,v in collections.Counter(str(r.get('energy_band')) for r in rows).most_common(): print(f"  {k:8s} {v:4d}  {v/N*100:5.1f}%")
sp=[r.get('energy_span') for r in rows if r.get('energy_span') is not None]
sp.sort()
print(f"  span p10={sp[int(.1*len(sp))]:.1f} p50={statistics.median(sp):.1f} p90={sp[int(.9*len(sp))]:.1f}  (真人 p50=37.0 p10=29.2)")
print("\n== F0 突跳：jump_max 分布（判八度区 10.5-13.5st）==")
fix=[r for r in rows if r.get('f0_jump_fix')]
print("  f0_jump_fix 条数:",len(fix))
jm=[r.get('f0_jump_max') for r in fix if r.get('f0_jump_max')]
jm.sort()
if jm:
    print(f"  jump_max  min={jm[0]:.1f} p25={jm[len(jm)//4]:.1f} 中位={statistics.median(jm):.1f} p75={jm[3*len(jm)//4]:.1f} max={jm[-1]:.1f}")
    b=collections.Counter()
    for x in jm:
        if 10.5<=x<=13.5: b['八度区 10.5-13.5（跟踪错）']+=1
        elif x<10.5: b['9-10.5（疑似真突跳）']+=1
        else: b['>13.5（真大跳）']+=1
    for k,v in b.items(): print(f"    {k:26s} {v}")
print("\n== FIX 是否只由 F0 突跳构成 ==")
fc=collections.Counter()
for r in fix:
    if r.get('f0_jump_fix'): fc['F0突跳']+=1
    if r.get('cut_hard'): fc['硬切']+=1
print("  ",dict(fc))
