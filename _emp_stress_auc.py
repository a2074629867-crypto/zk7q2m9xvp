# -*- coding: utf-8 -*-
"""EmphaClass 能不能当真重音检测器：同一批标注上算 AUC（尺子与 _stress_loop3 完全一致）"""
import json, glob, numpy as np

EMP = '_emp_narr_all.json'
WOLD = '_wl_words.json'
STOP = set('a an the and or but if of to in on at for with from by as is was were be been it its he she they his her their this that these those i you we not no so then than there here do did does have has had will would can could'.split())

emp = {x['id']: x for x in json.load(open(EMP, encoding='utf-8'))}
wold = json.load(open(WOLD, encoding='utf-8'))
stress = {}
for f in sorted(glob.glob('_ann/out_full/narr/ds/*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        stress[it['sid']] = it.get('stress') or []

vals, labs, pcts = [], [], []
nann = nword = nsent = 0
for sid in sorted(stress):
    e = emp.get(sid)
    w = wold.get('G:/_setup/_audio_ch123/out/%s.wav' % sid)
    if not e or not w:
        continue
    p = np.asarray(e['p'], float)
    dur = float(e['dur'])
    words = w['words']
    nw = len(words)
    if nw < 3 or len(p) < 8:
        continue
    sc = []
    for x in words:
        a = int(round(x['start'] / dur * len(p)))
        b = int(round(x['end'] / dur * len(p)))
        b = min(len(p), max(a + 1, b))
        seg = p[max(0, a):b]
        sc.append(float(seg.mean()) if len(seg) else 0.0)
    sc = np.asarray(sc)
    is_stop = np.array([wd['w'].lower().strip('.,;:!?') in STOP for wd in words])
    sidx = [s['tok'] for s in stress[sid] if s['tok'] < nw and not is_stop[s['tok']]]
    if not sidx:
        continue
    lab = np.zeros(nw, int)
    lab[sidx] = 1
    keep = ~is_stop
    k = int(keep.sum())
    if k < 3:
        continue
    vals.extend(sc[keep].tolist())
    labs.extend(lab[keep].tolist())
    order = np.argsort(-sc[keep])
    r = np.empty(k, int)
    r[order] = np.arange(1, k + 1)
    pct = 1.0 - (r - 1) / max(1, k - 1)
    pos = {int(i): j for j, i in enumerate(np.flatnonzero(keep))}
    pcts.extend([float(pct[pos[i]]) for i in sidx])
    nann += len(sidx)
    nword += k
    nsent += 1

vals = np.asarray(vals)
labs = np.asarray(labs)

def auc(v, l):
    pos = v[l == 1]
    neg = v[l == 0]
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind='mergesort')
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    n1, n0 = len(pos), len(neg)
    u = ranks[:n1].sum() - n1 * (n1 + 1) / 2.0
    return u / (n1 * n0)

print('句子 %d  内容词 %d  标注重读 %d' % (nsent, nword, nann))
print('EmphaClass 词级强调概率  AUC = %.3f   标注词平均百分位 %.1f%%' %
      (auc(vals, labs), 100 * np.mean(pcts)))
# 双峰度：阈值 0.5 时的 precision/recall
pred = vals > 0.5
tp = int(((pred == 1) & (labs == 1)).sum()); fp = int(((pred == 1) & (labs == 0)).sum())
fn = int(((pred == 0) & (labs == 1)).sum())
print('p>0.5 判重读：hit %d / miss %d / 误报 %d  precision %.2f  recall %.2f' %
      (tp, fn, fp, tp / max(1, tp + fp), tp / max(1, tp + fn)))
print('值域 min %.3f p25 %.3f 中位 %.3f p75 %.3f max %.3f' %
      (vals.min(), np.percentile(vals, 25), np.median(vals), np.percentile(vals, 75), vals.max()))
