# -*- coding: utf-8 -*-
"""按"标注强度"抽稀：只留标注值最慢的若干档当种子，再看段长分布。"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

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

wl = sorted(white, key=lambda s: pos[s])
regions, a, b = [], wl[0], wl[0]
for s in wl[1:]:
    if pos[s] - pos[b] <= 2:
        b = s
    else:
        regions.append((pos[a], pos[b]))
        a = b = s
regions.append((pos[a], pos[b]))

for TH in (0.77, 0.78, 0.79):
    seeds = {s for s in white if s in ann and ann[s] <= TH + 1e-9}
    for BRIDGE in (1, 2):
        f = [0] * len(order)
        for a, b in regions:
            seg = [1 if order[k] in seeds else 0 for k in range(a, b + 1)]
            for k in range(len(seg)):
                if seg[k]:
                    continue
                l = k - 1
                while l >= 0 and not seg[l] and k - l <= BRIDGE:
                    l -= 1
                r = k + 1
                while r < len(seg) and not seg[r] and r - k <= BRIDGE:
                    r += 1
                if l >= 0 and r < len(seg) and seg[l] and seg[r] and (r - l - 1) <= BRIDGE:
                    seg[k] = 1
            for k in range(a, b + 1):
                f[k] = seg[k - a]
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
        print('TH<=%.2f seed=%d bridge%d: 慢句 %d 段 %d 段长 %s'
              % (TH, len(seeds), BRIDGE, sum(f), len(runs),
                 dict(sorted(Counter(b - a + 1 for a, b in runs).items()))))
