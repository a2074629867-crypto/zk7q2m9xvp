import json, csv, io
W={json.loads(l)['tid']:json.loads(l) for l in io.open('_wl_flags60.jsonl',encoding='utf-8')}
P={json.loads(l)['tid']:json.loads(l) for l in io.open('_wl_flags60_pk.jsonl',encoding='utf-8')}
print('whisper %d  parakeet %d'%(len(W),len(P)))
print('\n== 覆盖率差异 >0.15 ==')
print('%-9s %6s %6s | %-28s | %-28s'%('tid','whis','pk','whisper 听到','parakeet 听到'))
for t in sorted(set(W)&set(P)):
    a,b=W[t],P[t]
    if abs(a['cov']-b['cov'])>0.15:
        print('%-9s %6.2f %6.2f | %-28s | %-28s'%(t,a['cov'],b['cov'],a['said'][:28],b['said'][:28]))
print('\n== 旗标差异 ==')
for t in sorted(set(W)&set(P)):
    a,b=set(W[t]['flags']),set(P[t]['flags'])
    if a!=b: print('%-9s whisper=%-22s parakeet=%-22s cov %.2f/%.2f'%(t,','.join(sorted(a)) or 'OK',','.join(sorted(b)) or 'OK',W[t]['cov'],P[t]['cov']))
print('\n== 只在 whisper 里出现的 tid ==', [t for t in W if t not in P])
