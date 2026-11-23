import json, collections
d=json.load(open(r'G:/_setup/_gate_dlg.json',encoding='utf-8'))
rows=d if isinstance(d,list) else (d.get('rows') or d.get('results') or [])
N=len(rows)
print("== reason code 频次（全量 %d）=="%N)
rc=collections.Counter()
for r in rows:
    for x in (r.get('reasons') or []):
        rc[x.get('code')]+=1
for k,v in rc.most_common(): print(f"  {k:20s} {v:4d}  {v/N*100:5.1f}%")

print("\n== note code 频次 ==")
nc=collections.Counter()
for r in rows:
    for x in (r.get('notes') or []):
        nc[x.get('code')]+=1
for k,v in nc.most_common(): print(f"  {k:20s} {v:4d}")

# wrong_speaker 细分：真正音色错 vs 短句不可判
ws=[r for r in rows if any((x.get('code')=='wrong_speaker') for x in (r.get('reasons') or []))]
print(f"\n== wrong_speaker 共 {len(ws)} 条，按时长分层 ==")
buckets=collections.Counter()
for r in ws:
    dur=(r.get('tech') or {}).get('dur') or 0
    if dur<1.0: buckets['<1.0s 声纹不可判']+=1
    elif dur<2.0: buckets['1.0-2.0s 临界']+=1
    else: buckets['>=2.0s 真音色错']+=1
for k,v in buckets.items(): print(f"  {k:22s} {v}")
print("\n  >=2.0s 的真音色错明细：")
for r in ws:
    dur=(r.get('tech') or {}).get('dur') or 0
    if dur>=2.0:
        sp=r.get('spk') or {}
        print(f"    {r['id']:10s} who={r['who']:8s} dur={dur:4.1f}s 判成={sp.get('role','?'):9s} z_target={sp.get('z_target')}  text={ (r.get('text') or '')[:50]}")

print("\n== tech REGEN 细分 ==")
tc=collections.Counter()
for r in rows:
    if (r.get('gates') or {}).get('tech')=='REGEN':
        for x in (r.get('reasons') or []):
            tc[x.get('code')]+=1
for k,v in tc.most_common(): print(f"  {k:20s} {v}")
