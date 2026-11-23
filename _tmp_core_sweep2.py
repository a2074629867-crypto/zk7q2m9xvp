# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
n = len(order)
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = float(o['rate'])
KEEP_FROM = {'c1_0001', 'c2_0244', 'c2_0285', 'c2_0316', 'c2_0345', 'c2_0377', 'c2_0394', 'c2_0406',
             'c2_0482', 'c2_0496', 'c3_0536', 'c3_0563', 'c3_0568', 'c3_0586', 'c3_0592', 'c3_0605',
             'c3_0621', 'c3_0657', 'c3_0678', 'c3_0700', 'c3_0755', 'c3_0765', 'c3_0783', 'c3_0817',
             'c3_0859', 'c3_0886', 'c3_0918', 'c3_0948'}


def runs_of(f):
    out, cur = [], None
    for k, v in enumerate(f):
        if v:
            if cur and k - cur[1] <= 1:
                cur[1] = k
            else:
                if cur:
                    out.append(cur)
                cur = [k, k]
    if cur:
        out.append(cur)
    return out


f = [1 if i in ann else 0 for i in order]
for k in range(1, n - 1):
    if not f[k] and f[k - 1] and f[k + 1]:
        f[k] = 1
for _ in range(4):
    bad = [(a, b) for a, b in runs_of(f) if b - a + 1 < 3]
    if not bad:
        break
    for a, b in bad:
        for step in range(1, 3 - (b - a + 1) + 1):
            if b + step < n and not f[b + step]:
                f[b + step] = 1
            elif a - step >= 0 and not f[a - step]:
                f[a - step] = 1
regions = [(a, b) for a, b in runs_of(f) if order[a] in KEEP_FROM]
print('白名单段', len(regions))

for CORE in (3, 4, 5, 6):
    for BRIDGE in (1, 2):
        g = [0] * n
        for a, b in regions:
            seeds = [k for k in range(a, b + 1) if order[k] in ann]
            if not seeds:
                continue
            cl, s, e = [], seeds[0], seeds[0]
            for k in seeds[1:]:
                if k - e <= 2:
                    e = k
                else:
                    cl.append((s, e))
                    s = e = k
            cl.append((s, e))
            for s, e in cl:
                idx = [k for k in range(s, e + 1) if order[k] in ann]
                vals = [ann[order[k]] for k in idx]
                L = min(CORE, len(idx))
                bi, bv = 0, None
                for i in range(len(idx) - L + 1):
                    v = sum(vals[i:i + L]) / L
                    if bv is None or v < bv - 1e-9:
                        bi, bv = i, v
                for k in idx[bi:bi + L]:
                    g[k] = 1
        for k in range(1, n - 1):
            if g[k]:
                continue
            l = k - 1
            while l >= 0 and not g[l] and k - l <= BRIDGE:
                l -= 1
            r = k + 1
            while r < n and not g[r] and r - k <= BRIDGE:
                r += 1
            if l >= 0 and r < n and g[l] and g[r] and (r - l - 1) <= BRIDGE:
                g[k] = 1
        runs = runs_of(g)
        print('CORE=%d BRIDGE=%d: 慢句 %d (%.1f%%) 段 %d 段长 %s'
              % (CORE, BRIDGE, sum(g), 100.0 * sum(g) / n, len(runs),
                 dict(sorted(Counter(b - a + 1 for a, b in runs).items()))))
