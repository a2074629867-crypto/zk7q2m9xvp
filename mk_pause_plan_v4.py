# -*- coding: utf-8 -*-
"""10-30 v4b 紧版：逗号/分号 0.85、段内句号 1.05、段末 1.55"""
import json, glob
COMMA, PERIOD, PARA = 0.85, 1.05, 1.55
phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
items = {}
for f in sorted(glob.glob('_ann/tasks_tier_full/batch_*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        items[it['sid']] = it
plan = {}; tot = 0.0; dist = {}
for sid in phys:
    it = items.get(sid)
    rows = []
    for s in (it.get('slots') or []):
        p = s['punct']
        d = COMMA if p in ',;:' else PERIOD   # 条内句号为 1.05；条末由拼接器给 1.55
        rows.append({'bid': s['bid'], 'tok': s['tok'], 'punct': p, 'd': d})
        tot += d; dist[d] = dist.get(d, 0) + 1
    plan[sid] = rows
json.dump(plan, open('_narr_pause_plan_v4.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
voiced = sum(x['voiced'] for x in phys.values()); words = sum(x['words'] for x in phys.values())
old_dur = sum(x['dur'] for x in phys.values())
n = sum(len(v) for v in plan.values())
print('槽位 %d  停顿 %.1fs  均值 %.2fs  分布 %s' % (n, tot, tot/n, dist))
print('旧 成品 %.0f wpm（停顿 %.1fs）' % (words/old_dur*60, old_dur-voiced))
print('新 成品 %.0f wpm（停顿 %.1fs）' % (words/(voiced+tot)*60, tot))
print('句内 voiced %.0f wpm（不变）' % (words/voiced*60))
