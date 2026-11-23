# -*- coding: utf-8 -*-
"""按 2026-10-29 pause_tiers.json 七档，给 716 条旁白出停顿计划（确定性，不调 LLM）
档位：zero 0 / marker 0.30 / list 0.40 / short 0.70 / dot_inner 0.85 / mid 1.16 / 句号 1.76
"""
import json, glob, statistics as st

ZERO, MARKER, LIST, SHORT, DOTIN, MID, LONG = 0.0, 0.30, 0.40, 0.70, 0.85, 1.16, 1.53
PERIOD_END = 1.76

MARKERS = {'well', 'anyway', 'so', 'now', 'oh', 'yes', 'no', 'then', 'still', 'of course'}

def words(s):
    return [w for w in s.replace(',', ' ').split() if w.strip()]

def target_for(slot, n_commas, comma_idx):
    p = slot['punct']
    left = words(slot['left']); right = words(slot['right'])
    lw, rw = len(left), len(right)
    if p in '.!?':
        return DOTIN, 'dot_inner'          # 条内句号（条间由拼接器给 1.76）
    if p in ';:':
        return 1.28, 'semicolon'
    if p in '—':
        return MID, 'dash'
    # 逗号
    if left and left[-1].lower() == 'like' and right and right[0].lower() in ('is', 'was'):
        return ZERO, 'zero'
    if right and right[0].lower() in MARKERS and rw <= 3:
        return MARKER, 'marker'
    if n_commas >= 3 and lw <= 3 and rw <= 3:
        return LIST, 'list'
    if lw <= 3 or rw <= 3:
        return SHORT, 'short'
    return MID, 'mid'

def main():
    items = []
    for f in sorted(glob.glob('_ann/tasks_tier_full/batch_*.json')):
        items += json.load(open(f, encoding='utf-8'))['items']
    print('句子数', len(items))
    phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
    plan = {}
    dist = {}
    tot_pause = 0.0
    for it in items:
        slots = it.get('slots') or []
        n_commas = sum(1 for s in slots if s['punct'] == ',')
        rows = []
        for i, s in enumerate(slots):
            d, tier = target_for(s, n_commas, i)
            rows.append({'bid': s['bid'], 'tok': s['tok'], 'punct': s['punct'], 'd': d, 'tier': tier})
            dist[tier] = dist.get(tier, 0) + 1
            tot_pause += d
        plan[it['sid']] = rows
    json.dump(plan, open('_narr_pause_plan_v3.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_slots = sum(len(v) for v in plan.values())
    print('槽位', n_slots, '停顿总时长 %.1fs' % tot_pause)
    print('档位分布', dict(sorted(dist.items(), key=lambda x: -x[1])))
    print('平均每处 %.2fs' % (tot_pause / max(1, n_slots)))
    # 预算：旧语音时长 + 新停顿
    old_sil = 0.0; voiced = 0.0; words_n = 0
    for sid, x in phys.items():
        voiced += x['voiced']; words_n += x['words']
        old_sil += x['dur'] - x['voiced']
    new_dur = voiced + tot_pause
    print()
    print('旧：停顿 %.1fs / 总 %.1fs / 成品 %.0f wpm' % (old_sil, voiced + old_sil, words_n / (voiced + old_sil) * 60))
    print('新：停顿 %.1fs / 总 %.1fs / 成品 %.0f wpm' % (tot_pause, new_dur, words_n / new_dur * 60))
    print('句内 voiced %.0f wpm（不变）' % (words_n / voiced * 60))

if __name__ == '__main__':
    main()
