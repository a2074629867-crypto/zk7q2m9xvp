# -*- coding: utf-8 -*-
import json, io, re, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = [r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator']
plan = {r['id']: r for r in plan}
ABBR = re.compile(r'\b(Mr|Mrs|Ms|Dr|St|Miss|Master)\.$', re.I)


def n_sent(t):
    # 按 .!? 数句子，排除缩写与省略号
    t = re.sub(r'\.\.\.', '…', t)
    parts = re.split(r'(?<=[.!?])\s+', t.strip())
    c = 0
    for p in parts:
        if not p.strip():
            continue
        if ABBR.search(p.strip()):
            continue
        c += 1
    return max(1, c)


cnt = Counter()
multi = []
for i, v in S.items():
    k = n_sent(plan[i]['text'])
    cnt[k] += 1
    if k > 1:
        multi.append((i, k, plan[i]['text'][:100]))
print('每个生成单位里包含几句：', dict(sorted(cnt.items())))
print('含 >=2 句的单位', len(multi), '/', len(S))
for m in multi[:8]:
    print('  ', m[0], m[1], m[2])
