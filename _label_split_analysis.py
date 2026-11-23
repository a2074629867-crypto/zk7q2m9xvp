"""在多候选里检验：除音色之外，韵律特征能否预测人工选择。

用法：G:/Python310/python.exe _label_split_analysis.py
"""
import json
import random

LAB = "G:/_setup/_mt_labels_live.json"
SC = "G:/_setup/_mt_score_ch%d.json"
CT = "G:/_setup/_mt_contour_ch%d.json"
CHS = (1, 2, 3)

FEATS = ['span_st', 'arc_st', 'start_st', 'end_st', 'peak_pos', 'tail25',
         'jump_cnt6', 'cov', 'n_breaks', 'e_peak_pos', 'e_range', 'e_head',
         'e_tail', 'ct_pen', 'voiced_s', 'dur', 'f0_med', 'e_std', 'tail300']
# 评分侧字段（不是韵律，用来对照：如果它们能预测，说明简单规则就够）
FEATS_SC = ['mos', 'spk', 'ratio', 'f0', 'wpm', 'centroid']
ALL_FEATS = FEATS + FEATS_SC


def load():
    lab = json.load(open(LAB, encoding='utf-8'))
    sc, ct = {}, {}
    for ch in CHS:
        for r in json.load(open(SC % ch, encoding='utf-8')):
            sc[r['id']] = r
        for uid, u in json.load(open(CT % ch, encoding='utf-8'))['units'].items():
            ct[uid] = u
    return lab, sc, ct


def pairs(lab, sc, ct):
    """返回 [(Δ重心, 选中候选的特征, 落选候选的特征)]，特征已合并轮廓+评分。"""
    out = []
    for uid, v in lab.items():
        p = str(v.get('pick'))
        r, u = sc.get(uid), ct.get(uid)
        if not r or not u or p in ('None', 'none'):
            continue
        cm = {str(c['seed']): c for c in r['cands']}
        cn = cm.get(p)
        if not cn:
            continue
        rej = [c for s, c in cm.items() if s != p]
        if not rej:
            continue
        q = min(rej, key=lambda c: abs(c['centroid'] - cn['centroid']))
        cu, qu = u['cands'].get(p), u['cands'].get(str(q['seed']))
        if cu and qu:
            w = dict(cu); w.update(cn)
            l = dict(qu); l.update(q)
            out.append((cn['centroid'] - q['centroid'], w, l))
    return out


def g(c, f):
    v = c.get(f)
    return None if v is None else float(v)


def maxacc(rows, feats=None):
    feats = feats or ALL_FEATS
    best = (0.0, '', '')
    for f in feats:
        for dr in (0, 1):
            ok = t = 0
            for row in rows:
                a, b = row[1], row[2]
                x, y = g(a, f), g(b, f)
                if x is None or y is None or x == y:
                    continue
                t += 1
                if (x < y) if dr == 0 else (x > y):
                    ok += 1
            if t >= 8:
                r = ok / t
                if r > best[0]:
                    best = (r, f, 'low' if dr == 0 else 'high')
    return best


def per_feature(rows, feats=None):
    feats = feats or ALL_FEATS
    res = []
    for f in feats:
        for dr in (0, 1):
            ok = t = 0
            for row in rows:
                x, y = g(row[1], f), g(row[2], f)
                if x is None or y is None or x == y:
                    continue
                t += 1
                if (x < y) if dr == 0 else (x > y):
                    ok += 1
            if t >= 8:
                res.append((ok / t, f, 'low' if dr == 0 else 'high', ok, t))
    return sorted(res, reverse=True)


def perm_test(rows, n=3000, seed=11, feats=None):
    random.seed(seed)
    obs = maxacc(rows, feats)[0]
    hits = 0
    vals = []
    for _ in range(n):
        perm = [(d, a, b) if random.random() < 0.5 else (d, b, a) for d, a, b in rows]
        r = maxacc(perm, feats)[0]
        vals.append(r)
        if r >= obs - 1e-9:
            hits += 1
    vals.sort()
    return obs, hits / n, vals


def main():
    lab, sc, ct = load()
    allp = pairs(lab, sc, ct)
    print('可用标注 %d 条' % len(allp))

    d = sorted(x[0] for x in allp)
    q = lambda f: d[min(len(d) - 1, int(f * (len(d) - 1)))]
    print('Δ重心(选中−落选): 中位 %+.0f  p10 %+.0f  p90 %+.0f'
          % (q(.5), q(.1), q(.9)))
    print()

    bands = [(-1e9, -300), (-300, -150), (-150, -50), (-50, 50),
             (50, 150), (150, 1e9)]
    print('%-16s %5s %7s' % ('Δ重心档', '条数', '占%'))
    for lo, hi in bands:
        n = sum(1 for x in allp if lo <= x[0] < hi)
        print('%-16s %5d %6.1f%%' % ('[%d,%d)' % (lo, hi), n, 100 * n / len(allp)))

    near = [x for x in allp if abs(x[0]) <= 150]
    print()
    print('近平子集 (|Δ重心|≤150Hz): %d 条 = %.0f%%'
          % (len(near), 100 * len(near) / len(allp)))

    for name, rows in (('全部 58 条', allp), ('近平 21 条', near)):
        print()
        print('=== %s ===' % name)
        for a, f, dr, ok, t in per_feature(rows)[:8]:
            print('  %-13s %-4s %2d/%2d = %3.0f%%' % (f, dr, ok, t, 100 * a))

    print()
    print('=== 置换检验（特征数: %d 轮廓 + %d 评分）===' % (len(FEATS), len(FEATS_SC)))
    for name, rows in (('全部 58 条', allp), ('近平 21 条', near)):
        for label, feats in (('仅轮廓', FEATS), ('轮廓+评分', ALL_FEATS)):
            obs, p, vals = perm_test(rows, feats=feats)
            best = maxacc(rows, feats)
            print('  %-8s %-9s 最优 %-12s %3.0f%%  零分布中位 %3.0f%% / p95 %3.0f%%  → p = %.3f'
                  % (name, label, best[1] + '/' + best[2], 100 * obs,
                     100 * vals[len(vals) // 2], 100 * vals[int(.95 * len(vals))], p))


if __name__ == '__main__':
    main()
