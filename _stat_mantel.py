# -*- coding: utf-8 -*-
"""
用文献标准统计量重测「结构/长度/重点 能不能预测韵律」。

三个工具（都不是自创）：
  1. Mantel test (Mantel 1967)          —— 两个距离矩阵的秩相关 + 置换检验
     语音学先例：Wieling & Nerbonne 2012 用它验证声学距离 vs 语言距离，r=0.61-0.79
  2. Partial Mantel (三矩阵)             —— 控制句长差之后，标签还有没有增量相关
  3. PERMANOVA / adonis2 (Anderson 2001) —— 距离矩阵上的方差分解，pseudo-F + R²

与旧口径的区别（旧口径为什么错）：
  旧：同 cell 的随机两句「平均而言」是否更近 → 接受集允许多峰时必然读出 0.5
  新：不要求每对点都近，只要求「标签越像 → 韵律越像」这一单调趋势（Mantel），
      以及「组间变异 / 组内变异」的比值（PERMANOVA）。

用法： python _stat_mantel.py [--ver new|old] [--rep contour|delta] [--perms 999]
"""
import json, sys, argparse, itertools
import numpy as np
from scipy.stats import rankdata, spearmanr

DOC = 'G:/_setup'


def flat_upper(D):
    n = D.shape[0]
    iu = np.triu_indices(n, 1)
    return D[iu], iu


def mantel(D1, D2, perms=999, seed=0):
    """Mantel test: Spearman rho between two distance matrices, permutation p."""
    n = D1.shape[0]
    iu = np.triu_indices(n, 1)
    a = D1[iu].astype(np.float64)
    b = D2[iu].astype(np.float64)
    ra = rankdata(a)
    rb = rankdata(b)
    ra = (ra - ra.mean()) / (ra.std() + 1e-12)
    rb = (rb - rb.mean()) / (rb.std() + 1e-12)
    rho = float(np.mean(ra * rb))

    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(perms):
        p = rng.permutation(n)
        D2p = D2[np.ix_(p, p)]
        bb = D2p[iu].astype(np.float64)
        rb2 = rankdata(bb)
        rb2 = (rb2 - rb2.mean()) / (rb2.std() + 1e-12)
        if abs(np.mean(ra * rb2)) >= abs(rho):
            cnt += 1
    pval = (cnt + 1) / (perms + 1)
    return rho, pval


def partial_mantel(D1, D2, Dctrl, perms=999, seed=0):
    """偏 Mantel：控制 Dctrl 之后 D1 与 D2 的偏相关（残差化 + 置换 D2）。"""
    n = D1.shape[0]
    iu = np.triu_indices(n, 1)

    def r(x):
        v = rankdata(x).astype(np.float64)
        return (v - v.mean()) / (v.std() + 1e-12)

    a = r(D1[iu]); b = r(D2[iu]); c = r(Dctrl[iu])
    # 残差化
    ab = a - c * np.mean(a * c)
    bb = b - c * np.mean(b * c)
    rho = float(np.mean(ab * bb) / (np.std(ab) * np.std(bb) + 1e-12))

    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(perms):
        p = rng.permutation(n)
        D2p = D2[np.ix_(p, p)]
        b2 = r(D2p[iu])
        bb2 = b2 - c * np.mean(b2 * c)
        if abs(np.mean(ab * bb2) / (np.std(ab) * np.std(bb2) + 1e-12)) >= abs(rho):
            cnt += 1
    return rho, (cnt + 1) / (perms + 1)


def permanova(D, groups, perms=9999, seed=0):
    """PERMANOVA (Anderson 2001)：距离矩阵平方和分解 + pseudo-F + 置换 p。"""
    D2 = D ** 2
    n = D2.shape[0]
    labels = np.asarray(groups)
    uniq = [g for g in dict.fromkeys(labels.tolist())]
    a = len(uniq)

    def ss_within(lab):
        tot = 0.0
        for g in dict.fromkeys(lab.tolist()):
            idx = np.where(lab == g)[0]
            ng = len(idx)
            if ng < 2:
                continue
            sub = D2[np.ix_(idx, idx)]
            tot += sub.sum() / ng
        return tot / 2.0

    ss_total = D2.sum() / (2.0 * n)
    ss_w = ss_within(labels)
    ss_a = ss_total - ss_w
    F = (ss_a / (a - 1)) / (ss_w / (n - a)) if ss_w > 0 else np.inf
    R2 = ss_a / ss_total

    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(perms):
        p = rng.permutation(labels)
        sw = ss_within(p)
        sa = ss_total - sw
        Fp = (sa / (a - 1)) / (sw / (n - a)) if sw > 0 else np.inf
        if Fp >= F:
            cnt += 1
    return dict(R2=float(R2), F=float(F), p=(cnt + 1) / (perms + 1), a=a, n=n)


def betadisper(D, groups):
    """组内离散度（到组内中心的平均距离），用 PERMDISP 的思路但只报描述值。"""
    labels = np.asarray(groups)
    out = {}
    for g in dict.fromkeys(labels.tolist()):
        idx = np.where(labels == g)[0]
        if len(idx) < 2:
            out[g] = (len(idx), np.nan)
            continue
        sub = D[np.ix_(idx, idx)]
        # 用 PCoA 前 k 维的中心近似；这里直接用平均距离（不依赖嵌入）
        out[g] = (len(idx), float(sub[np.triu_indices(len(idx), 1)].mean()))
    return out


def knn_cv(Z, labels, k=5, folds=5, seed=0):
    """kNN 分类 + 分层交叉验证，报 balanced accuracy。"""
    labels = np.asarray(labels)
    classes = list(dict.fromkeys(labels.tolist()))
    if len(classes) < 2:
        return None
    rng = np.random.default_rng(seed)
    idx_by_c = {c: np.where(labels == c)[0] for c in classes}
    fold_of = np.empty(len(labels), dtype=int)
    for c, idx in idx_by_c.items():
        perm = rng.permutation(idx)
        fold_of[perm] = np.arange(len(perm)) % folds
    correct = {c: 0 for c in classes}
    total = {c: 0 for c in classes}
    for f in range(folds):
        te = np.where(fold_of == f)[0]
        tr = np.where(fold_of != f)[0]
        if len(te) == 0 or len(tr) == 0:
            continue
        d = ((Z[te][:, None, :] - Z[tr][None, :, :]) ** 2).sum(-1)
        nn = np.argsort(d, axis=1)[:, :k]
        for i, ti in enumerate(te):
            votes = labels[tr][nn[i]]
            pred = max(set(votes.tolist()), key=lambda v: (votes == v).sum())
            total[labels[ti]] += 1
            if pred == labels[ti]:
                correct[labels[ti]] += 1
    accs = [correct[c] / total[c] for c in classes if total[c] > 0]
    return float(np.mean(accs)), len(classes)


def build(ver='new', rep='contour', npts=32, min_dur=0.12, min_frames=5):
    P = json.load(open(f'{DOC}/_prosody5_all.json', encoding='utf-8'))
    L = json.load(open(f'{DOC}/_cells_llm.json', encoding='utf-8'))
    ids = sorted(k.split('|')[0] for k in P if k.endswith('|' + ver))

    def usable(w):
        return (w['f0_med_rel'] is not None and w['dur'] >= min_dur
                and w['voiced_ratio'] * (w['dur'] / 0.01) >= min_frames)

    seqs, keep = [], []
    for sid in ids:
        w = P[f'{sid}|{ver}']['words']
        v = [x['f0_med_rel'] for x in w if usable(x)]
        if len(v) < 3:
            continue
        v = np.asarray(v, float)
        v = v - v.mean()
        if v.std() < 1e-6:
            continue
        if rep == 'delta':
            v = np.diff(v)
            if len(v) < 2:
                continue
        # 时间/词序归一化到 npts 点
        x = np.linspace(0, len(v) - 1, npts)
        r = np.interp(x, np.arange(len(v)), v)
        r = (r - r.mean()) / (r.std() + 1e-9)
        seqs.append(r)
        keep.append(sid)

    Z = np.array(seqs)
    D = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1))

    # 标签
    struct = [L[s]['struct'] for s in keep]
    focus = [L[s]['focus'] for s in keep]
    scene = [L[s]['scene'] for s in keep]
    nw = [len(P[f'{s}|{ver}']['words']) for s in keep]

    def lenband(n):
        return '<=8' if n <= 8 else ('9-17' if n <= 17 else ('18-27' if n <= 27 else '>=28'))

    lens = [lenband(n) for n in nw]
    cells = [f'{a}|{b}|{c}' for a, b, c in zip(struct, lens, focus)]
    return dict(ids=keep, D=D, Z=Z, struct=struct, focus=focus, scene=scene,
                lens=lens, cells=cells, nw=nw)


def labdist(vals):
    """标签距离矩阵：相同 0，不同 1（Hamming）。"""
    v = np.asarray(vals)
    return (v[:, None] != v[None, :]).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ver', default='new')
    ap.add_argument('--rep', default='contour')
    ap.add_argument('--perms', type=int, default=999)
    args = ap.parse_args()

    B = build(args.ver, args.rep)
    n = len(B['ids'])
    D = B['D']
    print(f'== {args.ver} / {args.rep}  句数 {n}  距离矩阵 {n}x{n}')
    nw = np.asarray(B['nw'], float)
    Dnw = np.abs(nw[:, None] - nw[None, :])
    print(f'句长 {int(nw.min())}-{int(nw.max())} 词，中位 {np.median(nw):.0f}')

    # 0) 混杂基线：韵律距离与句长差的相关
    rho0, p0 = mantel(D, Dnw, perms=args.perms)
    print(f'\n[0] 韵律距离 ~ |句长差|        Mantel rho={rho0:+.3f}  p={p0:.4f}')

    rows = []
    for name, vals in (('struct', B['struct']), ('len', B['lens']),
                       ('focus', B['focus']), ('scene', B['scene']),
                       ('cell', B['cells'])):
        Lm = labdist(vals)
        rho, p = mantel(D, Lm, perms=args.perms)
        prho, pp = partial_mantel(D, Lm, Dnw, perms=args.perms)
        pv = permanova(D, vals, perms=min(9999, args.perms * 10))
        rows.append((name, rho, p, prho, pp, pv))
        print(f'[{name}] Mantel rho={rho:+.3f} p={p:.4f} | 偏Mantel(控句长) rho={prho:+.3f} p={pp:.4f} '
              f'| PERMANOVA R2={pv["R2"]:.3f} F={pv["F"]:.2f} p={pv["p"]:.4f}')

    # kNN 可预测性
    print('\nkNN 交叉验证（balanced accuracy）:')
    for name, vals in (('struct', B['struct']), ('len', B['lens']),
                       ('focus', B['focus']), ('cell', B['cells'])):
        r = knn_cv(B['Z'], vals, k=5, folds=5)
        if r:
            acc, nc = r
            print(f'  {name:<7} {nc} 类  balanced acc = {acc*100:.1f}%   随机 {100/nc:.1f}%')

    # 组内离散度：哪个 cell 真的「模板多」
    bd = betadisper(D, B['cells'])
    big = [(g, c, d) for g, (c, d) in bd.items() if c >= 8]
    big.sort(key=lambda x: -x[2])
    allw = [d for g, (c, d) in bd.items() if c >= 8]
    print(f'\n组内平均距离（≥8 句的 {len(big)} 个 cell）: 中位 {np.nanmedian(allw):.3f}')
    print('  最分散 3 个:', [(g, c, round(d, 2)) for g, c, d in big[:3]])
    print('  最紧凑 3 个:', [(g, c, round(d, 2)) for g, c, d in big[-3:]])
    print(f'  整体组内平均 {np.mean(allw):.3f}  vs  全体平均 {D[np.triu_indices(n,1)].mean():.3f}')

    json.dump(dict(n=n, ver=args.ver, rep=args.rep,
                   confound=dict(rho=rho0, p=p0),
                   tests=[dict(name=r[0], mantel_rho=r[1], mantel_p=r[2],
                               partial_rho=r[3], partial_p=r[4], permanova=r[5]) for r in rows],
                   dispersion={g: dict(n=c, mean_d=d) for g, (c, d) in bd.items()}),
              open(f'{DOC}/_stat_mantel_{args.ver}_{args.rep}.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'\n→ _stat_mantel_{args.ver}_{args.rep}.json')


if __name__ == '__main__':
    main()
