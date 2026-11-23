# -*- coding: utf-8 -*-
import json, io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = [r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator']

pat = re.compile(r'\b(alone|by himself|to himself|shaking|shook|trembl|choking|choked|his eyes|face down|head down|curled|huddled|shiver)\b', re.I)
for r in plan:
    if pat.search(r['text']):
        v = S.get(r['id'], {})
        if v.get('rate', 1) >= 1:
            print('%s  rate=%s | %s' % (r['id'], v.get('rate'), r['text'][:120]))
