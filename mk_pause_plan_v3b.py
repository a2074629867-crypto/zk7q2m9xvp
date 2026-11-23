# -*- coding: utf-8 -*-
"""两个口径对比（只算 716 条有音频的）：A=马修七档  B=普通朗读基线"""
import json, glob

phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
items = []
for f in sorted(glob.glob('_ann/tasks_tier_full/batch_*.json')):
    items += json.load(open(f, encoding='utf-8'))['items']
items = [it for it in items if it['sid'] in phys]
print('有音频且有计划', len(items), '/ 任务总数', len(items))

MARKERS = {'well','anyway','so','now','oh','yes','no','then','still'}
def w(s): return [x for x in s.replace(',',' ').split() if x.strip()]

def tier(slot, n_comma, mode):
    p = slot['punct']; L = w(slot['left']); R = w(slot['right']); lw, rw = len(L), len(R)
    if mode == 'A':
        if p in '.!?': return 0.85, 'dot_inner'
        if p in ';:': return 1.28, 'semicolon'
        if p in '—': return 1.16, 'dash'
        if L and L[-1].lower()=='like' and R and R[0].lower() in ('is','was'): return 0.0,'zero'
        if R and R[0].lower() in MARKERS and rw<=3: return 0.30,'marker'
        if n_comma>=3 and lw<=3 and rw<=3: return 0.40,'list'
        if lw<=3 or rw<=3: return 0.70,'short'
        return 1.16,'mid'
    else:  # B 普通朗读
        if p in '.!?': return 0.70, 'period'
        if p in ';:': return 0.50, 'semicolon'
        if p in '—': return 0.35, 'dash'
        if L and L[-1].lower()=='like' and R and R[0].lower() in ('is','was'): return 0.0,'zero'
        if R and R[0].lower() in MARKERS and rw<=3: return 0.15,'marker'
        if n_comma>=3 and lw<=3 and rw<=3: return 0.20,'list'
        if lw<=3 or rw<=3: return 0.35,'short'
        return 0.45,'mid'

voiced = sum(x['voiced'] for x in phys.values()); wordsn = sum(x['words'] for x in phys.values())
old_dur = sum(x['dur'] for x in phys.values())
print('句内 voiced %.0f wpm（不变）；旧总时长 %.1fs；旧成品 %.0f wpm' % (wordsn/voiced*60, old_dur, wordsn/old_dur*60))

for mode, name in [('A','A 马修七档'), ('B','B 普通朗读')]:
    tot = 0.0; dist = {}
    for it in items:
        ncomma = sum(1 for s in it.get('slots') or [] if s['punct']==',')
        for s in it.get('slots') or []:
            d, t = tier(s, ncomma, mode)
            tot += d; dist[t] = dist.get(t,0)+1
    n = sum(dist.values())
    print()
    print('%s：槽位 %d，停顿 %.1fs，均值 %.2fs，成品 %.0f wpm' % (name, n, tot, tot/n, wordsn/(voiced+tot)*60))
    print('   分布', dict(sorted(dist.items(), key=lambda x:-x[1])))
# 句间/段落层（不在条内）
print()
print('注：段落 2.0-2.5s 发生在句子之间，由拼接器负责，不在这 1646 个槽位里')
