# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = [r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator']
idx = {r['id']: k for k, r in enumerate(plan)}

for center in ['c2_0397', 'c3_0893']:
    k = idx[center]
    print('==== around', center)
    for j in range(max(0, k - 5), min(len(plan), k + 6)):
        r = plan[j]
        v = S.get(r['id'], {})
        mark = '>>' if r['id'] == center else '  '
        print('%s %s rate=%s run=%s | %s' % (mark, r['id'], v.get('rate'), v.get('run'), r['text'][:96]))
    print()
