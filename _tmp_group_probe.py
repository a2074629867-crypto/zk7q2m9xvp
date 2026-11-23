# -*- coding: utf-8 -*-
"""把 <=5 词的碎句并进相邻句，形成"一口气"句组；rate 在句组上统一。"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SHORT = 5
d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
order = [i for b in json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8')) for i in b['ids']]
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
wc = {i: len(plan[i]['text'].split()) for i in order}

groups, cur = [], []
for i in order:
    cur.append(i)
    if wc[i] > SHORT:
        groups.append(cur)
        cur = []
if cur:
    if groups:
        groups[-1].extend(cur)
    else:
        groups.append(cur)

print('句组 %d 个（原 716 句）；组大小分布 %s' % (len(groups), dict(sorted(Counter(len(g) for g in groups).items()))))
slow_wavs = 0
slow_groups = 0
for g in groups:
    head = max(g, key=lambda i: wc[i])
    if any(S[i]['rate'] < 1 for i in g):
        slow_groups += 1
        slow_wavs += len(g)
print('慢句组 %d 个，涉及 wav %d 个（原 98）' % (slow_groups, slow_wavs))
print()
print('样例（哭泣那段）：')
gid = {i: k for k, g in enumerate(groups) for i in g}
for g in groups:
    if 'c2_0394' in g or 'c2_0395' in g or 'c2_0396' in g or 'c2_0397' in g:
        tag = '慢' if any(S[i]['rate'] < 1 for i in g) else '—'
        print('  [%s] %s' % (tag, ' '.join(plan[i]['text'] for i in g)[:150]))
