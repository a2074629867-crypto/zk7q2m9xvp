import json, collections
rows=json.load(open(r'G:/_setup/_narr_check/_narr_check.json',encoding='utf-8'))
N=len(rows)
print("== 旁白 verdict（%d 条）=="%N)
c=collections.Counter(r.get('verdict') for r in rows)
for k,v in c.most_common(): print(f"  {k:10s} {v:4d}  {v/N*100:5.1f}%")
print("\n== 触发项频次 ==")
wc=collections.Counter()
for r in rows:
    for x in (r.get('why') or []):
        s=str(x)
        # 修乱码
        try: s=s.encode('latin-1').decode('gbk')
        except Exception: pass
        wc[s]+=1
for k,v in wc.most_common(20): print(f"  {k:34s} {v}")
print("\n== cut_hard / cut_drop 分布 ==")
hard=[r for r in rows if r.get('cut_hard')]
print("  cut_hard=True:", len(hard))
drops=[r.get('cut_drop') for r in rows if r.get('cut_drop') is not None]
drops.sort()
if drops:
    import statistics
    print(f"  cut_drop n={len(drops)} min={drops[0]:.1f} p25={drops[len(drops)//4]:.1f} 中位={statistics.median(drops):.1f} p75={drops[3*len(drops)//4]:.1f} max={drops[-1]:.1f}")
    print("  >96dB 的条数:", sum(1 for x in drops if x>96))
print("\n== energy_band 分布 ==")
eb=collections.Counter(r.get('energy_band') for r in rows)
for k,v in eb.most_common(): print(f"  {k:10s} {v:4d}")
print("\n== FIX 的构成 ==")
fix=[r for r in rows if r.get('verdict')=='FIX']
print("  FIX 共", len(fix))
fc=collections.Counter()
for r in fix:
    if r.get('cut_hard'): fc['结尾硬切']+=1
    if r.get('f0_jump_fix'): fc['F0突跳']+=1
for k,v in fc.items(): print(f"    {k:12s} {v}")
