# -*- coding: utf-8 -*-
"""试算：GAP=1 + 只保留查尔斯相关段，看慢句总数能否落到 ~208（原来 416 的一半）。"""
import json, io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = o
n = len(order)
hit = [1 if i in ann else 0 for i in order]
EMO = re.compile(r'(他|男孩|恐惧|害怕|羞耻|羞辱|委屈|哭|泪|痛|孤|绝望|认命|忌妒|嫉|愤怒|恨|死亡|临终|回忆)')


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


GAP = 1
f = hit[:]
for k in range(1, n - 1):
    if f[k]:
        continue
    l = k - 1
    while l >= 0 and not f[l] and k - l <= GAP:
        l -= 1
    r = k + 1
    while r < n and not f[r] and r - k <= GAP:
        r += 1
    if l >= 0 and r < n and f[l] and f[r] and (r - l - 1) <= GAP:
        f[k] = 1
for _ in range(4):
    rr = runs_of(f)
    bad = [(a, b) for a, b in rr if b - a + 1 < 3]
    if not bad:
        break
    for a, b in bad:
        for step in range(1, 3 - (b - a + 1) + 1):
            if b + step < n and not f[b + step]:
                f[b + step] = 1
            elif a - step >= 0 and not f[a - step]:
                f[a - step] = 1

rr = runs_of(f)
print('GAP=1 基础：慢句 %d  段 %d' % (sum(f), len(rr)))

keep = [0] * n
kept, dropped = [], []
for a, b in rr:
    ids = order[a:b + 1]
    k_hit = sum(1 for i in ids if 'Kingshaw' in plan[i]['text'])
    e_hit = sum(1 for i in ids if i in ann and EMO.search(ann[i].get('why', '')))
    n_ann = sum(1 for i in ids if i in ann)
    ok = (k_hit >= 1 or e_hit >= 2) and n_ann >= 2
    (kept if ok else dropped).append((a, b, len(ids), k_hit, e_hit, n_ann))
    if ok:
        for k in range(a, b + 1):
            keep[k] = 1

print('保留 %d 段 / 慢句 %d   丢掉 %d 段 / %d 句'
      % (len(kept), sum(keep), len(dropped), sum(x[2] for x in dropped)))
print('\n-- 保留（按位置）')
for a, b, m, k, e, na in kept:
    print('  %s-%s  %2d 句  K=%d emo=%d ann=%d | %s' % (order[a], order[b], m, k, e, na, plan[order[a]]['text'][:58]))
print('\n-- 丢掉')
for a, b, m, k, e, na in dropped:
    print('  %s-%s  %2d 句  K=%d emo=%d ann=%d | %s' % (order[a], order[b], m, k, e, na, plan[order[a]]['text'][:58]))
