# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
pos = {s: k for k, s in enumerate(order)}
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = float(o['rate'])
KEEP_FROM = {'c1_0001', 'c2_0244', 'c2_0285', 'c2_0316', 'c2_0345', 'c2_0377', 'c2_0394', 'c2_0406',
             'c2_0482', 'c2_0496', 'c3_0536', 'c3_0563', 'c3_0568', 'c3_0586', 'c3_0592', 'c3_0605',
             'c3_0621', 'c3_0657', 'c3_0678', 'c3_0700', 'c3_0755', 'c3_0765', 'c3_0783', 'c3_0817',
             'c3_0859', 'c3_0886', 'c3_0918', 'c3_0948'}
cur = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))['sentences']
white = {s for s, v in cur.items() if v.get('run')}
seeds_all = sorted([s for s in white if s in ann], key=lambda s: pos[s])
clusters, a, b = [], seeds_all[0], seeds_all[0]
for s in seeds_all[1:]:
    if pos[s] - pos[b] <= 2:
        b = s
    else:
        clusters.append((pos[a], pos[b]))
        a = b = s
clusters.append((pos[a], pos[b]))

for CORE in (3, 4, 5):
    g = [0] * len(order)
    for a, b in clusters:
        idx = [k for k in range(a, b + 1) if order[k] in ann]
        vals = [ann[order[k]] for k in idx]
        L = min(CORE, len(idx))
        bi, bv = 0, None
        for i in range(len(idx) - L + 1):
            v = sum(vals[i:i + L]) / L
            if bv is None or v < bv - 1e-9:
                bi, bv = i, v
        for k in idx[bi:bi + L]:
            g[k] = 1
    for k in range(1, len(g) - 1):
        if not g[k] and g[k - 1] and g[k + 1]:
            g[k] = 1
    runs, c = [], None
    for k, v in enumerate(g):
        if v:
            if c and k - c[1] <= 1:
                c[1] = k
            else:
                if c:
                    runs.append(c)
                c = [k, k]
    if c:
        runs.append(c)
    print('CORE=%d: 慢句 %d (%.1f%%) 段 %d 段长 %s' % (CORE, sum(g), 100.0 * sum(g) / len(g), len(runs),
                                               dict(sorted(Counter(b - a + 1 for a, b in runs).items()))))
