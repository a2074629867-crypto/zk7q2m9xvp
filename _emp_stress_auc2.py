# -*- coding: utf-8 -*-
"""EmphaClass 多种聚合 + 强弱标签，看是不是换个口径就能救回来"""
import json, glob, numpy as np
STOP = set('a an the and or but if of to in on at for with from by as is was were be been it its he she they his her their this that these those i you we not no so then than there here do did does have has had will would can could'.split())
emp = {x['id']: x for x in json.load(open('_emp_narr_all.json', encoding='utf-8'))}
wold = json.load(open('_wl_words.json', encoding='utf-8'))
stress = {}
for f in sorted(glob.glob('_ann/out_full/narr/ds/*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        stress[it['sid']] = it.get('stress') or []

def auc(v, l):
    v = np.asarray(v, float); l = np.asarray(l, int)
    pos, neg = v[l == 1], v[l == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind='mergesort')
    ranks = np.empty(len(allv), float); ranks[order] = np.arange(1, len(allv) + 1)
    n1, n0 = len(pos), len(neg)
    return (ranks[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0)

AGG = ['mean', 'max', 'frac50', 'top3']
for lvmin in (1, 2):
    res = {a: ([], []) for a in AGG}
    for sid in sorted(stress):
        e = emp.get(sid); w = wold.get('G:/_setup/_audio_ch123/out/%s.wav' % sid)
        if not e or not w: continue
        p = np.asarray(e['p'], float); dur = float(e['dur']); words = w['words']; nw = len(words)
        if nw < 3 or len(p) < 8: continue
        is_stop = np.array([x['w'].lower().strip('.,;:!?') in STOP for x in words])
        sidx = [s['tok'] for s in stress[sid] if s['tok'] < nw and not is_stop[s['tok']] and s.get('level', 1) >= lvmin]
        if not sidx: continue
        lab = np.zeros(nw, int); lab[sidx] = 1
        keep = ~is_stop
        if keep.sum() < 3: continue
        per = {a: [] for a in AGG}
        for i, x in enumerate(words):
            a0 = max(0, int(round(x['start'] / dur * len(p))))
            b0 = min(len(p), max(a0 + 1, int(round(x['end'] / dur * len(p)))))
            seg = np.sort(p[a0:b0])[::-1] if b0 > a0 else np.array([0.0])
            per['mean'].append(seg.mean()); per['max'].append(seg[0])
            per['frac50'].append(float((seg > 0.5).mean()))
            per['top3'].append(float(seg[:3].mean()))
        for a in AGG:
            v = np.asarray(per[a])
            res[a][0].extend(v[keep].tolist()); res[a][1].extend(lab[keep].tolist())
    print('level>=%d  n_ann=%d n_neg=%d' % (lvmin, int(np.sum(res['mean'][1])), int(len(res['mean'][1]) - np.sum(res['mean'][1]))))
    for a in AGG:
        print('   %-7s AUC %.3f' % (a, auc(res[a][0], res[a][1])))
