# -*- coding: utf-8 -*-
"""把两路投票结果落成句级 rate 表（2026-11-20）。

输入：rate_groups_vote.json（hy4 + ds 两路，两票全 1 才算慢）
输出：rate_llm_narr.json（句级，含 group/run）、rate_narr_sent_v1.json（扁平）
"""
import json, io, sys
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = 1.00
SLOW = 0.84
P = r'G:/_setup'

cur = json.load(open(P + '/rate_llm_narr.json', encoding='utf-8'))
S = cur['sentences']
order = [i for b in json.load(open(P + '/_narr_blocks.json', encoding='utf-8')) for i in b['ids']]
grp = {i: S[i]['group'] for i in order}

vote = json.load(open(P + '/rate_groups_vote.json', encoding='utf-8'))
slow_g = {r['gid'] for r in vote['items'] if r['slow'] == 1}
why_g = {r['gid']: r.get('why', '') for r in vote['items']}

sents = {}
for i in order:
    g = grp[i]
    rec = {'rate': SLOW if g in slow_g else BASE, 'group': g}
    if g in slow_g:
        rec['why'] = why_g.get(g, '')
    sents[i] = rec

# runs（连续慢句子）
runs, c = [], None
for k, i in enumerate(order):
    if sents[i]['rate'] < 1:
        if c and k - c[1] <= 1:
            c[1] = k
        else:
            if c:
                runs.append(c)
            c = [k, k]
    elif c:
        runs.append(c)
        c = None
if c:
    runs.append(c)

run_id = {}
for si, (a, b) in enumerate(runs, 1):
    for k in range(a, b + 1):
        run_id[order[k]] = 'R%02d' % si
for i in order:
    if i in run_id:
        sents[i]['run'] = run_id[i]

gsz = Counter(len([x for x in order if grp[x] == g]) for g in {grp[i] for i in order})
slow_n = sum(1 for i in order if sents[i]['rate'] < 1)
slow_groups = len(slow_g)
runs_g = Counter(len({grp[order[k]] for k in range(a, b + 1)}) for a, b in runs)

meta = dict(cur['_meta'])
meta.update({
    'unit': 'sentence-group（一口气：<=5 词的碎句并进下一句；组内同一 rate）',
    'derived_from': 'hy4(global:hy4free) + ds(deepseek-v4.1-flash) 两路独立标注，两票全 1 才判慢',
    'rule': '两路投票：全 1 = 慢 0.84；1 票 = 记 disputed 但不慢；0 票 = 1.00',
    'n_sent': len(order),
    'n_slow': slow_n,
    'n_slow_groups': slow_groups,
    'n_groups': len({grp[i] for i in order}),
    'n_runs': len(runs),
    'n_disputed': vote['_meta'].get('n_disputed', 0),
    'coverage_words': None,
})
out = {'_meta': meta, 'sentences': sents}
json.dump(out, open(P + '/rate_llm_narr.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
json.dump({'_meta': {'base_rate': BASE, 'slow_rate': SLOW, 'unit': 'sentence-group'},
           'rates': {i: sents[i]['rate'] for i in order}},
          open(P + '/rate_narr_sent_v1.json', 'w', encoding='utf-8'), ensure_ascii=False)

print('慢组 %d/%d  慢句 %d/%d (%.1f%%)  段 %d'
      % (slow_groups, meta['n_groups'], slow_n, len(order), 100.0 * slow_n / len(order), len(runs)))
print('每段的句组数分布', dict(sorted(runs_g.items())))
print('组大小分布', dict(sorted(gsz.items())))
