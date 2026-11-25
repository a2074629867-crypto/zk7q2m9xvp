# -*- coding: utf-8 -*-
"""
韵律空间里到底有没有「类型」？
  有类型 → 「模板 / 接受集 A、B」成立
  没类型（连续谱）→ 只能按「正确的区间」判（用户原话）

三个标准检验（都不是自创）：
  1. Hopkins statistic   （聚类倾向：0.5=均匀随机，→1=强聚类）
  2. Silhouette vs k     （Kaufman & Rousseeuw 1990；<0.1 通常认为无实质聚类结构）
  3. 距离分布的单峰性     （KDE 峰数 + 偏度；多峰 ⇒ 存在亚群）
"""
import json, sys
import numpy as np
from numpy.random import default_rng
from scipy.stats import skew, kurtosis, gaussian_kde

DOC = 'G:/_setup'


def hopkins(Z, m=None, seed=0):
    """Hopkins 统计量（版本 1，无放回）。H≈0.5 随机，H>0.75 有聚类倾向。"""
    n, d = Z.shape
    if m is None:
        m = max(10, n // 10)
    rng = default_rng(seed)
    idx = rng.choice(n, m, replace=False)
    lo, hi = Z.min(0), Z.max(0)

    def nn_dist_to_data(P):
        # P: (m,d) → 每个点到数据集（除自身）的最近距离
        out = np.empty(len(P))
        for i, p in enumerate(P):
            d2 = ((Z - p) ** 2).sum(1)
            d2[idx[i]] = np.inf
            out[i] = np.sqrt(d2.min())
        return out

    u = nn_dist_to_data(Z[idx])
    P = rng.uniform(lo, hi, size=(m, d))
    w = np.empty(m)
    for i, p in enumerate(P):
        w[i] = np.sqrt(((Z - p) ** 2).sum(1).min())
    H = u.sum() / (u.sum() + w.sum())
    return float(H)


def silhouette_kmeans(Z, k, seed=0, iters=80):
    """简化 KMeans + silhouette（不依赖 sklearn）。"""
    rng = default_rng(seed)
    n = len(Z)
    C = Z[rng.choice(n, k, replace=False)]
    lab = np.zeros(n, int)
    for _ in range(iters):
        d = ((Z[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        new = d.argmin(1)
        if (new == lab).all() and _ > 0:
            break
        lab = new
        for j in range(k):
            m = lab == j
            if m.any():
                C[j] = Z[m].mean(0)
    D = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1))
    s = np.zeros(n)
    for i in range(n):
        same = np.where(lab == lab[i])[0]
        same = same[same != i]
        if len(same) == 0:
            continue
        a = D[i, same].mean()
        b = min(D[i, lab == j].mean() for j in range(k) if j != lab[i] and (lab == j).any())
        s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0
    return float(s.mean()), lab


def dist_shape(D):
    """距离分布：是否多峰。"""
    n = D.shape[0]
    v = D[np.triu_indices(n, 1)]
    xs = np.linspace(v.min(), v.max(), 400)
    dens = gaussian_kde(v, bw_method=0.15)(xs)
    # 找局部极大
    pk = [i for i in range(1, len(xs) - 1) if dens[i] > dens[i - 1] and dens[i] > dens[i + 1]]
    # 只保留明显峰（高度 > 最大值 10%）
    pk = [i for i in pk if dens[i] > 0.10 * dens.max()]
    return dict(mean=float(v.mean()), std=float(v.std()), cv=float(v.std() / v.mean()),
                skew=float(skew(v)), kurt=float(kurtosis(v)),
                n_peaks=len(pk), peaks=[float(xs[i]) for i in pk], n_pairs=len(v))


def main():
    B = json.load(open(f'{DOC}/_stat_mantel_new_contour.json', encoding='utf-8'))
    # 需要矩阵本身：重算
    sys.path.insert(0, DOC)
    from _stat_mantel import build
    res = {}
    for rep in ('contour', 'delta'):
        b = build('new', rep)
        Z, D, n = b['Z'], b['D'], len(b['ids'])
        print(f'\n===== {rep}  n={n}')
        H = hopkins(Z, seed=1)
        print(f'Hopkins H = {H:.3f}   （0.5=随机均匀，>0.75 有聚类倾向）')
        sil = {}
        for k in (2, 3, 4, 6, 8, 12):
            s, _ = silhouette_kmeans(Z, k, seed=1)
            sil[k] = s
            print(f'  KMeans k={k:<3} silhouette={s:+.3f}')
        ds = dist_shape(D)
        print(f'距离分布: 均值 {ds["mean"]:.2f} 标准差 {ds["std"]:.2f} CV={ds["cv"]:.3f} '
              f'偏度 {ds["skew"]:+.2f} 峰数 {ds["n_peaks"]} @ {[round(x,1) for x in ds["peaks"]]}')
        res[rep] = dict(n=n, hopkins=H, silhouette=sil, dist=ds)
    json.dump(res, open(f'{DOC}/_stat_structure.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n→ _stat_structure.json')


if __name__ == '__main__':
    main()
