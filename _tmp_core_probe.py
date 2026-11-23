# -*- coding: utf-8 -*-
"""v4 试算：每个连续标注簇只取"最慢的 <=3 句"作为核心，再桥接短插段。"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CORE = 3
B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
pos = {s: k for k, s in enumerate(order)}
cur = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))['sentences']
white = {s for s, v in cur.items() if v.get('run')}
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = float(o['rate'])

seeds = sorted([s for s in white if s in ann], key=lambda s: pos[s])
# 连续簇
clusters, a, b = [], seeds[0], seeds[0]
for s in seeds[1:]:
    if pos[s] - pos[b] <= 2:
        b = s
    else:
        clusters.append((pos[a], pos[b]))
        a = b = s
clusters.append((pos[a], pos[b]))
print('连续标注簇 %d 个，总标注句 %d' % (len(clusters), len(seeds)))

cores = []
for a, b in clusters:
    idx = [k for k in range(a, b + 1) if order[k] in ann]
    vals = [ann[order[k]] for k in idx]
    L = min(CORE, len(idx))
    best, bs = None, 0
    for i in range(len(idx) - L + 1):
        s = sum(vals[i:i + L]) / L
        if best is None or s < best - 1e-9:
            best, bs = s, i
    cores.append(idx[bs:bs + L])

for BRIDGE in (0, 1, 2):
    f = [0] * len(order)
    for c in cores:
        for k in c:
            f[k] = 1
    if BRIDGE:
        for k in range(1, len(f) - 1):
            if f[k]:
                continue
            l = k - 1
            while l >= 0 and not f[l] and k - l <= BRIDGE:
                l -= 1
            r = k + 1
            while r < len(f) and not f[r] and r - k <= BRIDGE:
                r += 1
            if l >= 0 and r < len(f) and f[l] and f[r] and (r - l - 1) <= BRIDGE:
                f[k] = 1
    runs, c = [], None
    for k, v in enumerate(f):
        if v:
            if c and k - c[1] <= 1:
                c[1] = k
            else:
                if c:
                    runs.append(c)
                c = [k, k]
    if c:
        runs.append(c)
    print('bridge%d: 慢句 %d (%.1f%%) 段 %d 段长 %s'
          % (BRIDGE, sum(f), 100.0 * sum(f) / len(f), len(runs),
             dict(sorted(Counter(b - a + 1 for a, b in runs).items()))))
