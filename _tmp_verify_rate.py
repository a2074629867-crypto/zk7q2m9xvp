# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
# 段长分布
runs = {}
for sid, v in S.items():
    if v.get('run'):
        runs.setdefault(v['run'], []).append(sid)
print('段数', len(runs), '段长分布', dict(sorted(Counter(len(v) for v in runs.values()).items())))
print('慢句', sum(1 for v in S.values() if v['rate'] < 1), '/', len(S))
print()
for rid in ['R01', 'R02', 'R13', 'R51']:
    ids = runs.get(rid, [])
    if not ids:
        continue
    print('%s  %d 句  %s → %s' % (rid, len(ids), ids[0], ids[-1]))
    for sid in ids[:2]:
        t = plan.get(sid, {}).get('text', '')
        print('    ', sid, t[:78])
    print()
