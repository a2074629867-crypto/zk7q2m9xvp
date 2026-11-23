# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
ids = sorted([i for i, v in S.items() if v.get('run') == 'R20'])
print('R20 %d 句：%s → %s' % (len(ids), ids[0], ids[-1]))
for i in ids:
    print('  ', i, S[i]['rate'], '|', plan[i]['text'])
