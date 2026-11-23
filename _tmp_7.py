import json, re
rows=[json.loads(l) for l in open('_castle_en_ch123_plan.jsonl',encoding='utf-8') if l.strip()]
by={r['id']:r for r in rows}
for sid in ['c1_0128','c1_0144','c1_0176','c2_0208','c2_0422','c2_0476','c3_0845']:
    r=by.get(sid)
    print('---',sid, r.get('speaker') if r else 'MISSING', 'len=%d'%len(r['text']) if r else '')
    if r: print('   ', repr(r['text']))
