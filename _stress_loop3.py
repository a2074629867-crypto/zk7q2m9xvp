# -*- coding: utf-8 -*-
"""重音闭环 v3：只用内容词（过滤虚词），指标：AUC / 百分位 / top-k / 该读没读"""
import json, os, glob
import numpy as np, soundfile as sf
import parselmouth

OUT_DIR = 'G:/_setup/_ann/out_full/narr/ds'
WOLD = 'G:/_setup/_wl_words.json'
NEW = 'G:/_setup/_audio_ch123/out'
OLD = 'G:/_setup/_audio_ch123/out_bak_prepause'
AX = ['dur', 'f0', 'eng']
STOP = set('a an the and or but if of to in on at for with from by as is was were be been it its he she they his her their this that these those i you we not no so then than there here do did does have has had will would can could'.split())

def gaps(y, sr):
    h = max(1, int(sr * 0.01))
    n = len(y) // h
    if n < 3:
        return []
    db = 20 * np.log10(np.sqrt((y[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12) + 1e-12)
    v = db > -35.0
    idx = np.flatnonzero(v)
    if len(idx) < 2:
        return []
    a, b = idx[0], idx[-1]
    out, i = [], a
    while i <= b:
        if not v[i]:
            j = i
            while j <= b and not v[j]:
                j += 1
            if (j - i) * 0.01 >= 0.40:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out

stress = {}
for f in sorted(glob.glob(OUT_DIR + '/*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        stress[it['sid']] = it.get('stress') or []
wold = json.load(open(WOLD, encoding='utf-8'))

A = {a: [] for a in AX}
P = {a: [] for a in AX}
top = {1: 0, 3: 0, 5: 0}
miss = []
n_ann = n_word = 0
for sid in sorted(stress):
    w = wold.get('G:/_setup/_audio_ch123/out/%s.wav' % sid)
    if not w:
        continue
    yo, sr = sf.read(os.path.join(OLD, sid + '.wav'), dtype='float32')
    yn, sr2 = sf.read(os.path.join(NEW, sid + '.wav'), dtype='float32')
    if yo.ndim > 1:
        yo = yo.mean(1)
    if yn.ndim > 1:
        yn = yn.mean(1)
    go, gn = gaps(yo, sr), gaps(yn, sr2)
    shift, acc = [], 0.0
    for i in range(min(len(go), len(gn))):
        acc += (gn[i][1] - gn[i][0]) - (go[i][1] - go[i][0])
        shift.append((go[i][1], acc))

    def mv(t):
        s = 0.0
        for e, a in shift:
            if t >= e:
                s = a
            else:
                break
        return t + s

    words = [(x['w'], mv(x['start']), mv(x['end'])) for x in w['words']]
    if len(words) < 3:
        continue
    snd = parselmouth.Sound(yn, sampling_frequency=sr2)
    pt = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f0 = pt.selected_array['frequency']
    ts = pt.xs()
    dur = np.array([max(1e-3, e - s) for _, s, e in words])
    eng = np.array([float(np.sqrt((yn[int(s*sr2):max(int(s*sr2)+1, int(e*sr2))] ** 2).mean() + 1e-12)) for _, s, e in words])
    f0w = []
    for _, s, e in words:
        mk = (ts >= s) & (ts <= e) & (f0 > 0)
        f0w.append(float(np.median(f0[mk])) if mk.any() else np.nan)
    mf = np.nanmedian(f0w) if np.any(~np.isnan(f0w)) else 0.0
    f0c = np.array([(x if not np.isnan(x) else mf) - mf for x in f0w])

    def rz(v):
        v = np.asarray(v, float)
        med = np.nanmedian(v)
        d = np.nanmedian(np.abs(v - med)) * 1.4826 + 1e-9
        return (v - med) / d

    z = {'dur': rz(np.log(dur)), 'f0': rz(f0c), 'eng': rz(np.log(eng))}
    nw = len(words)
    is_stop = np.array([wd[0].lower().strip('.,;:!?') in STOP for wd in words])
    pct, rk = {}, {}
    for a in AX:
        order = np.argsort(-z[a])
        r = np.empty(nw, int)
        r[order] = np.arange(1, nw + 1)
        rk[a] = r
        pct[a] = 1.0 - (r - 1) / max(1, nw - 1)
    sidx = [s['tok'] for s in stress[sid] if s['tok'] < nw and not is_stop[s['tok']]]
    if not sidx:
        continue
    lab = np.zeros(nw, int)
    lab[sidx] = 1
    n_ann += len(sidx)
    n_word += nw
    for a in AX:
        A[a].extend(list(zip(z[a].tolist(), lab.tolist())))
        for i in sidx:
            P[a].append(float(pct[a][i]))
    for i in sidx:
        best = min(rk[a][i] for a in AX)
        for k in top:
            if best <= k:
                top[k] += 1
        ps = [float(pct[a][i]) for a in AX]
        if all(p < 0.5 for p in ps):
            miss.append({'sid': sid, 'w': words[i][0], 'p': [round(p, 2) for p in ps]})


def auc(pairs):
    pos = [v for v, l in pairs if l == 1]
    neg = [v for v, l in pairs if l == 0]
    if not pos or not neg:
        return 0.5
    allv = np.array(pos + neg)
    r = np.argsort(np.argsort(allv)) + 1
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


print('内容词标注重读 %d 处 / 总词 %d' % (n_ann, n_word))
print()
for a in AX:
    print('%-4s AUC %.3f   标注词平均百分位 %.1f%%' % (a, auc(A[a]), 100 * float(np.mean(P[a]))))
print()
for k in [1, 3, 5]:
    print('至少一轴进句中 top%d: %d (%.1f%%)' % (k, top[k], 100 * top[k] / max(1, n_ann)))
print()
print('该读没读（三轴全<50%%）: %d (%.1f%%)' % (len(miss), 100 * len(miss) / max(1, n_ann)))
print('样例', json.dumps(miss[:6], ensure_ascii=False))
json.dump({'n_ann': n_ann, 'n_word': n_word, 'auc': {a: auc(A[a]) for a in AX},
           'mean_pct': {a: float(np.mean(P[a])) for a in AX},
           'top': {str(k): v for k, v in top.items()}, 'miss': miss},
          open('G:/_setup/_stress_loop_report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
