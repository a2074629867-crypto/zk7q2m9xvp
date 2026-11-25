# -*- coding: utf-8 -*-
"""
给「20 句判定页」打分 —— 检验闸与听感的相关性。

判读规则（**事先定好，不许事后改**）：
  AUC >= 0.75  且  Spearman rho >= 0.45   → 闸有效，150 句照做
  0.60 <= AUC < 0.75                      → 弱：只用于排序挑候选，不进验收线
  AUC < 0.60                              → 闸作废，删除 P1/P2 验收线，改人工抽检
"""
import json, sys
import numpy as np
from scipy.stats import spearmanr

DOC = 'G:/_setup'


def load_vote():
    recs = []
    for line in open(f'{DOC}/_ab_votes.jsonl', encoding='utf-8'):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if 'judge20' not in r.get('body', ''):
            continue
        try:
            recs.append(json.loads(r['body']))
        except Exception:
            continue
    return recs[-1] if recs else None


def auc(neg, pos):
    """P(随机一个 pos 的分数 > 随机一个 neg 的分数)，并列算 0.5。"""
    if not pos or not neg:
        return float('nan')
    win = 0.0
    for p in pos:
        for n in neg:
            win += 1.0 if p > n else (0.5 if p == n else 0.0)
    return win / (len(pos) * len(neg))


def main():
    v = load_vote()
    if not v:
        print('还没收到投票。请在页面上评完并提交（或把页面底部的 JSON 贴给我）。')
        return
    items = {x['id']: x for x in json.load(open(f'{DOC}/_judge20_items.json', encoding='utf-8'))}
    rows = []
    for it in v.get('items', []):
        if it.get('v') is None:
            continue
        m = items.get(it['id'])
        if not m:
            continue
        rows.append(dict(id=it['id'], v=it['v'], note=it.get('note', ''),
                         score=m['_score'], grp=m['_grp'], p1=m['_p1'], tail=m['_tail']))
    if len(rows) < 8:
        print(f'有效评分只有 {len(rows)} 条，样本太少，先不判。')
        return

    print(f'有效评分 {len(rows)} / {len(items)}\n')
    print(f'{"档":<8}{"n":>4}{"平均评分":>10}{"难受占比":>9}{"顺占比":>8}')
    name = {0: '顺', 1: '有点怪', 2: '难受'}
    for g in ('high', 'mid', 'clean'):
        s = [r for r in rows if r['grp'] == g]
        if not s:
            continue
        vv = np.array([r['v'] for r in s])
        print(f'{g:<8}{len(s):>4}{vv.mean():>10.2f}{np.mean(vv == 2)*100:>8.0f}%{np.mean(vv == 0)*100:>7.0f}%')

    sc = np.array([r['score'] for r in rows], float)
    rt = np.array([r['v'] for r in rows], float)
    rho, p = spearmanr(sc, rt)
    good = [r['score'] for r in rows if r['v'] == 0]
    bad = [r['score'] for r in rows if r['v'] == 2]
    a = auc(good, bad)
    print(f'\nSpearman rho(闸分数, 你的评分) = {rho:+.3f}  p={p:.3f}')
    print(f'AUC(顺 vs 难受) = {a:.3f}   n_顺={len(good)}  n_难受={len(bad)}')

    print('\n逐句：')
    for r in sorted(rows, key=lambda x: -x['score']):
        print(f"  {r['id']:<9} {name[r['v']]:<4} score={r['score']:<2} 组={r['grp']:<5} "
              f"功能词峰={r['p1']:<2} tail={r['tail']:<2} {r['note'][:28]}")

    print('\n判定（规则事先定好）：')
    if a >= 0.75 and rho >= 0.45:
        print('  ✅ 闸有效 → 150 句照做（阶段 A）')
    elif a >= 0.60:
        print('  ⚠️ 弱相关 → 只用于排序挑候选，P1/P2 不进验收线')
    else:
        print('  ❌ 闸作废 → 删除 P1/P2 验收线，改人工抽检（另出方案）')


if __name__ == '__main__':
    main()
