# -*- coding: utf-8 -*-
import json, io, sys, statistics
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
plan = [r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator']
para = {r['id']: (r['chapter'], r['para']) for r in plan}

np_list = []
for b in B:
    ps = {para[i] for i in b['ids'] if i in para}
    np_list.append(len(ps))

print('每块跨原文段落数: min %d / 中位 %s / max %d' % (min(np_list), statistics.median(np_list), max(np_list)))
from collections import Counter
print('分布', dict(sorted(Counter(np_list).items())))
print('每块句数 中位', statistics.median([b['n'] for b in B]), '词 中位', statistics.median([b['words'] for b in B]))
