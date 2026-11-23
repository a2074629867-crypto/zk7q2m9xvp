# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_castle_en_ch123_plan_v3.jsonl', encoding='utf-8') if l.strip())}
narr = [r for r in plan.values() if r.get('speaker') == 'narrator']

print('== 句级 rate 表')
for ch in ['c1', 'c2', 'c3']:
    ids = [i for i in S if i.startswith(ch)]
    slow = sum(1 for i in ids if S[i]['rate'] < 1)
    print('  %s  慢 %d/%d = %.1f%%' % (ch, slow, len(ids), 100.0 * slow / len(ids)))

print()
print('== 生产计划里的 rate 还是旧值？')
diff = sum(1 for r in narr if abs(float(r.get('rate') or 1) - S[r['id']]['rate']) > 1e-6)
print('  计划行 %d，与新表不一致 %d 行' % (len(narr), diff))
print('  计划 rate 分布', dict(sorted(Counter(round(float(r.get('rate') or 1), 2) for r in narr).items())))

print()
print('== 三张表有没有 consumer')
import os, re
files = [f for f in os.listdir(r'G:/_setup') if f.endswith('.py')]
def who(name):
    hits = []
    for f in files:
        try:
            t = open(os.path.join(r'G:/_setup', f), encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        if name in t:
            hits.append(f)
    return hits
for name in ['rate_narr_sent_v1.json', 'rate_llm_narr.json', 'stress_llm_narr.json', 'pause_llm_narr_v3.json']:
    print('  %-26s -> %s' % (name, who(name) or '（没有脚本读）'))
