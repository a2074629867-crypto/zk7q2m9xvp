import json, collections, statistics
rows=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
print("== too_short 时长分布 ==")
ts=[r for r in rows if any(x.get('code')=='too_short' for x in (r.get('reasons') or []))]
d=[(r.get('tech') or {}).get('dur') or 0 for r in ts]
print(" n=%d  min=%.2f 中位=%.2f max=%.2f"%(len(d),min(d),statistics.median(d),max(d)))
print(" <0.6s:",sum(1 for x in d if x<0.6)," 0.6-1.0s:",sum(1 for x in d if 0.6<=x<1.0)," >=1.0s:",sum(1 for x in d if x>=1.0))
print("\n== role_ambiguous 明细（前 20）==")
ra=[r for r in rows if any(x.get('code')=='role_ambiguous' for x in (r.get('reasons') or []))]
for r in ra[:20]:
    sp=r.get('spk') or {}
    print(f"  {r['id']:10s} who={r['who']:8s} dur={((r.get('tech') or {}).get('dur') or 0):4.1f}s role_gap={sp.get('role_gap')} z_target={sp.get('z_target')} z_other={sp.get('z_other')} text={(r.get('text') or '')[:40]}")
print("\n== role_ambiguous 的 role_gap 分布 ==")
g=[(r.get('spk') or {}).get('role_gap') for r in ra if (r.get('spk') or {}).get('role_gap') is not None]
if g:
    g.sort(); print("  min=%.2f 中位=%.2f max=%.2f"%(g[0],statistics.median(g),g[-1]))
    print("  gap>0（其实判对了但差距小）:",sum(1 for x in g if x>0))
print("\n== hard_cut note 的 tech 值 ==")
hc=[r for r in rows if any(x.get('code')=='hard_cut' for x in (r.get('notes') or []))]
print(" n=",len(hc))
for r in hc[:8]:
    t=r.get('tech') or {}
    print(f"  {r['id']:10s} tail_db={t.get('tail_db')} rms_db={t.get('rms_db')} dur={t.get('dur')}")
