# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
order = [i for b in json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8')) for i in b['ids']]
wc = {i: len(plan[i]['text'].split()) for i in order}
print('词数分布', dict(sorted(Counter(min(wc[i], 12) for i in order).items())))
short = [i for i in order if wc[i] <= 4]
print('<=4 词的句子', len(short))
print('其中现在被标慢的', sum(1 for i in short if S[i]['rate'] < 1))
for i in short[:25]:
    print('  %s %d 词 rate=%s | %s' % (i, wc[i], S[i]['rate'], plan[i]['text'][:60]))
