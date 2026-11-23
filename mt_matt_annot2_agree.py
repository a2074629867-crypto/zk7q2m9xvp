# -*- coding: utf-8 -*-
"""mt_matt_annot2_agree.py —— 第二轮（句内二分）三方一致性 + 时长分离检验。

与第一轮 agree 脚本的区别：
1. 第一轮比的是 5 档 / 3 档的 Kappa，目的是"能不能用"。
2. 本轮的目的是**检验二分假设本身**：inner 与 bound 在实测时长上是否真的分离。
   - 若两类时长分布重叠严重（AUC≈0.5），说明"句法层级决定时长"是错的，
     应退回单档 + R3 连续修正。
   - 若 AUC 高（≥0.75），说明二分成立，可以给两类不同 base 值。
3. 同时报 clause / para，检查句末档是否稳定（第一轮 para 只有 5 条）。
"""
import collections
import itertools
import json
import sys

import numpy as np

S = r'G:/_setup/_matt_annot2_samples.json'
FILES = [
    ('main', r'G:/_setup/_annot2_matt_main.json'),
    ('hy4', r'G:/_setup/_annot2_matt_hy4.json'),
    ('ds', r'G:/_setup/_annot2_matt_ds.json'),
]
TIERS = ['inner', 'bound', 'clause', 'para']


def load(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print('  !! 读不到 %s: %s' % (path, e))
        return None
    return {k: v['kind'] for k, v in d.items()}


def fleiss(kappa_tab):
    """kappa_tab: n_items × n_cats 的计数矩阵。"""
    m = kappa_tab.sum(axis=1)
    if (m == 0).any():
        keep = m > 0
        kappa_tab, m = kappa_tab[keep], m[keep]
    N, n = kappa_tab.shape[0], kappa_tab.sum(axis=1)[0]
    P_i = ((kappa_tab ** 2).sum(axis=1) - n) / (n * (n - 1))
    P_bar = P_i.mean()
    p_j = kappa_tab.sum(axis=0) / (N * n)
    P_e = (p_j ** 2).sum()
    k = (P_bar - P_e) / (1 - P_e) if P_e < 1 else float('nan')
    return k, P_bar, P_e, N


def auc(pos, neg):
    """P(随机正样本 > 随机负样本)，用秩和算。"""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # 处理并列
    vals, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    for i, c in enumerate(cnt):
        if c > 1:
            ranks[inv == i] = ranks[inv == i].mean()
    r_pos = ranks[:len(pos)].sum()
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def main():
    samples = {r['key']: r for r in json.load(open(S, encoding='utf-8'))}
    gaps = {k: v['_gap'] for k, v in samples.items()}

    ann = {}
    for name, p in FILES:
        a = load(p)
        if a:
            ann[name] = a
            miss = [k for k in samples if k not in a]
            print('%-5s n=%d  %s%s' % (name, len(a),
                                       dict(collections.Counter(a.values())),
                                       ('  缺 %d 条' % len(miss)) if miss else ''))
    names = list(ann)

    keys = [k for k in samples if all(k in ann[n] for n in names)]

    # ---- 全档一致性
    print('\n=== 全档一致性（%d 条 × %d 人）===' % (len(keys), len(names)))
    tab = np.zeros((len(keys), len(TIERS)))
    idx = {t: i for i, t in enumerate(TIERS)}
    for r, k in enumerate(keys):
        for n in names:
            tab[r, idx[ann[n][k]]] += 1
    k5, pb, pe, N = fleiss(tab)
    print('全 %d 档: Kappa=%.3f  P_bar=%.3f  P_e=%.3f  N=%d' % (len(TIERS), k5, pb, pe, N))
    agree_all = sum(1 for r in range(len(keys))
                    if len(set(ann[n][keys[r]] for n in names)) == 1)
    print('  全一致 %d/%d = %.0f%%' % (agree_all, len(keys), 100.0 * agree_all / len(keys)))

    # ---- 二分一致性：只取所有标为 inner/bound 的条目
    sub = [k for k in keys if all(ann[n][k] in ('inner', 'bound') for n in names)]
    print('\n=== 句内二分一致性（%d 条）===' % len(sub))
    if len(sub) >= 3:
        t2 = np.zeros((len(sub), 2))
        for r, k in enumerate(sub):
            for n in names:
                t2[r, 0 if ann[n][k] == 'inner' else 1] += 1
        k2, pb2, pe2, N2 = fleiss(t2)
        print('inner/bound: Kappa=%.3f  P_bar=%.3f  P_e=%.3f  N=%d' % (k2, pb2, pe2, N2))

    # ---- 两两一致性
    print('\n=== 两两一致率（全档 / 句内二分）===')
    for a, b in itertools.combinations(names, 2):
        allag = np.mean([ann[a][k] == ann[b][k] for k in keys])
        both = [k for k in keys if ann[a][k] in ('inner', 'bound') and ann[b][k] in ('inner', 'bound')]
        ib = np.mean([ann[a][k] == ann[b][k] for k in both]) if both else float('nan')
        print('  %-5s vs %-5s  全档 %.2f   inner/bound %.2f (n=%d)' % (a, b, allag, ib, len(both)))

    # ---- 关键检验：每类的实测时长分布 + AUC
    print('\n=== 时长分离检验（用 main 的标注分组）===')
    print('%-7s %4s %6s %6s %6s %6s %6s' % ('tier', 'n', 'p10', 'p50', 'p90', 'min', 'max'))
    grp = {}
    for k in keys:
        t = ann['main'][k]
        grp.setdefault(t, []).append(gaps[k])
    for t in TIERS:
        g = np.array(grp.get(t, []))
        if len(g) == 0:
            print('%-7s %4d  (无)' % (t, 0))
            continue
        print('%-7s %4d %6.2f %6.2f %6.2f %6.2f %6.2f' % (
            t, len(g), np.percentile(g, 10), np.median(g),
            np.percentile(g, 90), g.min(), g.max()))
    if 'inner' in grp and 'bound' in grp:
        a = auc(grp['bound'], grp['inner'])
        print('\n  AUC(bound > inner) = %.3f' % a)
        print('  → 0.5 = 完全不可分；0.75+ = 二分成立；>0.9 = 强分离')
        # 各类之间的重叠区间
        gi, gb = np.array(grp['inner']), np.array(grp['bound'])
        print('  inner 上界 %.2f  bound 下界 %.2f  重叠 %d 条' % (
            gi.max(), gb.min(),
            int(((gi > gb.min()) & (gi < gb.max())).sum() +
                ((gb > gi.min()) & (gb < gi.max())).sum())))
    if 'clause' in grp:
        a2 = auc(grp['clause'], grp.get('bound', []))
        print('  AUC(clause > bound) = %.3f' % a2)

    # ---- 单调性：各标注者的档位中位时长是否单调
    print('\n=== 各标注者档位中位时长（单调性检查）===')
    for n in names:
        med = []
        for t in TIERS:
            g = [gaps[k] for k in keys if ann[n][k] == t]
            med.append((t, len(g), np.median(g) if g else float('nan')))
        print('  %-5s %s' % (n, '  '.join(
            ('%s %.2f(n=%d)' % (m[0], m[2], m[1])) if m[1] else ('%s --(n=0)' % m[0])
            for m in med)))


if __name__ == '__main__':
    main()
