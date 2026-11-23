# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
W = {}
for b in B:
    for i in b['ids']:
        W[i] = b['words'] / max(1, len(b['ids']))
ann = {json.loads(l)['sid'] for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8') if l.strip()}
hit = [1 if i in ann else 0 for i in order]
n = len(order)
print('句数', n, '标注', sum(hit))


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


def fill_gaps(f, gap):
    # 只在两段标注之间填，不向两端外扩
    for k in range(1, n - 1):
        if f[k]:
            continue
        l = k - 1
        while l >= 0 and not f[l] and k - l <= gap:
            l -= 1
        r = k + 1
        while r < n and not f[r] and r - k <= gap:
            r += 1
        if l >= 0 and r < n and f[l] and f[r] and (r - l - 1) <= gap:
            f[k] = 1
    return f


for GAP in (0, 1, 2, 3):
    f = hit[:]
    if GAP:
        f = fill_gaps(f, GAP)
    rr = runs_of(f)
    cov = sum(W[order[k]] for k in range(n) if f[k]) / sum(W.values())
    print('GAP<=%d: 慢句 %d (%.1f%%)  词 %.1f%%  段 %d  单句段 %d  段长中位 %s  最短 %d'
          % (GAP, sum(f), 100.0 * sum(f) / n, 100 * cov, len(rr),
             sum(1 for a, b in rr if a == b),
             sorted([b - a + 1 for a, b in rr])[len(rr) // 2], min(b - a + 1 for a, b in rr)))
