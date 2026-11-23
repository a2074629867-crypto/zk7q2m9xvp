# -*- coding: utf-8 -*-
import json, io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

d = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))
S = d['sentences']
plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = o

runs = {}
for sid, v in S.items():
    if v.get('run'):
        runs.setdefault(v['run'], []).append(sid)

EMO = re.compile(r'(他|男孩|恐惧|害怕|羞耻|羞辱|委屈|哭|泪|痛|孤|绝望|认命|忌妒|嫉|愤怒|恨|死|临终|回忆)')
for rid in sorted(runs):
    ids = runs[rid]
    n = len(ids)
    n_ann = sum(1 for i in ids if i in ann)
    king = sum(1 for i in ids if 'Kingshaw' in plan[i]['text'])
    emo = sum(1 for i in ids if i in ann and EMO.search(ann[i].get('why', '')))
    head = plan[ids[0]]['text'][:64].replace('\n', ' ')
    print('%s n=%2d ann=%2d(%.0f%%) K=%2d emo=%2d | %s' % (rid, n, n_ann, 100.0 * n_ann / n, king, emo, head))
print('总慢句', sum(len(v) for v in runs.values()))
