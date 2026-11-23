# -*- coding: utf-8 -*-
import json, io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = [r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator']

pat = re.compile(r'\b(cried|crying|cry|wept|weeping|sob|sobbed|sobbing|tears|tearful|in tears)\b', re.I)
for r in plan:
    if pat.search(r['text']):
        sid = r['id']
        rt = S.get(sid, {}).get('rate')
        run = S.get(sid, {}).get('run')
        print('%s  rate=%s run=%s | %s' % (sid, rt, run, r['text'][:110]))
