# -*- coding: utf-8 -*-
"""自包含：按 2026-10-30 v4b 紧版重铺 716 条旁白停顿。
v5：条内逗号 0.70s、条内句号 0.85s（用户 2026-11-15 纠正：1.16 是条间口径，不得进条内）。只改内部静音，不动语音。
"""
import json, os, glob, statistics as st
import numpy as np, soundfile as sf

SRC = 'G:/_setup/_audio_ch123/out_bak_prepause'
OUT = 'G:/_setup/_audio_ch123/out_v5'
BAK = 'G:/_setup/_audio_ch123/out_bak_prepause'
COMMA, PERIOD, THR, MINGAP = 0.70, 0.85, -35.0, 0.40

phys = {x['id']: x for x in json.load(open('_narr_phys.json', encoding='utf-8'))}
items = {}
for f in sorted(glob.glob('_ann/tasks_tier_full/batch_*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        items[it['sid']] = it

plan = {}
for sid in phys:
    rows = []
    for s in (items.get(sid, {}).get('slots') or []):
        rows.append({'punct': s['punct'], 'd': COMMA if s['punct'] in ',;:' else PERIOD})
    plan[sid] = rows
from collections import Counter
cc=Counter(x['punct'] for v in plan.values() for x in v)
print('slots punct', dict(cc))
os.makedirs(OUT, exist_ok=True)


def gaps_of(y, sr):
    h = max(1, int(sr * 0.01))
    n = len(y) // h
    if n < 3:
        return []
    db = 20 * np.log10(np.sqrt((y[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12) + 1e-12)
    v = db > THR
    idx = np.flatnonzero(v)
    if len(idx) < 2:
        return []
    a, b = idx[0], idx[-1]
    out = []
    i = a
    while i <= b:
        if not v[i]:
            j = i
            while j <= b and not v[j]:
                j += 1
            if (j - i) * 0.01 >= MINGAP:
                out.append((int(i * 0.01 * sr), int(j * 0.01 * sr)))
            i = j
        else:
            i += 1
    return out


def bed_of(y, sr, gaps):
    win = int(0.1 * sr)
    if len(y) < win * 3:
        return np.zeros(win, dtype=np.float32)
    mask = np.ones(len(y), dtype=bool)
    for s, e in gaps:
        mask[max(0, s - win // 2):min(len(y), e + win // 2)] = False
    best, bestr = None, 1e9
    for i in range(0, len(y) - win, win):
        if not mask[i:i+win].all():
            continue
        r = float(np.sqrt((y[i:i+win] ** 2).mean()))
        if 1e-7 < r < bestr:
            best, bestr = y[i:i+win], r
    return best.astype(np.float32) if best is not None else np.zeros(win, dtype=np.float32)


def rebuild(y, sr, gaps, targets, bed):
    out = []
    prev = 0
    for (gs, ge), want in zip(gaps, targets):
        out.append(y[prev:gs])
        sil = y[gs:ge]
        cur = len(sil)
        want_n = max(1, int(round(want * sr)))
        if want_n < cur - 10:
            cut = cur - want_n
            a = (cur - cut) // 2
            out.append(np.concatenate([sil[:a], sil[a+cut:]]))
        elif want_n > cur + 10:
            add = want_n - cur
            a = cur // 2
            fill = np.tile(bed, int(np.ceil(add / max(1, len(bed)))))[:add] if len(bed) else np.zeros(add, dtype=np.float32)
            r = max(1, int(0.005 * sr))
            if len(fill) > 2 * r:
                fill[:r] *= np.linspace(0, 1, r)
                fill[-r:] *= np.linspace(1, 0, r)
            out.append(np.concatenate([sil[:a], fill, sil[a:]]))
        else:
            out.append(sil)
        prev = ge
    out.append(y[prev:])
    return np.concatenate(out)


stat = {'exact': 0, 'mapped': 0, 'nogap': 0}
for sid in sorted(phys):
    f = os.path.join(SRC, sid + '.wav')
    if not os.path.exists(f):
        continue
    y, sr = sf.read(f, dtype='float32')
    if y.ndim > 1:
        y = y.mean(1)
    g = gaps_of(y, sr)
    slots = plan[sid]
    if not g:
        stat['nogap'] += 1
        targets = []
    elif len(g) == len(slots):
        stat['exact'] += 1
        targets = [s['d'] for s in slots]
    else:
        stat['mapped'] += 1
        G, S = len(g), len(slots)
        targets = ([slots[int(round(i * (S - 1) / (G - 1))) if G > 1 else 0]['d'] for i in range(G)] if S else [COMMA] * G)
    y2 = rebuild(y, sr, g, targets, bed_of(y, sr, g))
    pk = float(np.abs(y2).max()) if len(y2) else 0.0
    if pk > 0.999:
        y2 = y2 * (0.99 / pk)
    sf.write(os.path.join(OUT, sid + '.wav'), y2, sr, subtype='PCM_16')
print('done', stat)

words = sum(x['words'] for x in phys.values())
for d in [BAK, OUT]:
    tot = voi = 0.0
    gaps = []
    peak = 0.0
    lev = []
    miss = 0
    for sid in phys:
        p = os.path.join(d, sid + '.wav')
        if not os.path.exists(p):
            miss += 1
            continue
        y, sr = sf.read(p, dtype='float32')
        if y.ndim > 1:
            y = y.mean(1)
        tot += len(y) / sr
        peak = max(peak, float(np.abs(y).max()))
        h = int(sr * 0.01)
        n = len(y) // h
        db = 20 * np.log10(np.sqrt((y[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12) + 1e-12)
        v = db > THR
        idx = np.flatnonzero(v)
        if len(idx) < 2:
            continue
        voi += len(idx) * 0.01
        lev.append(float(np.sqrt((y[:n*h].reshape(n, h)[v].astype(np.float64) ** 2).mean())))
        a, b = idx[0], idx[-1]
        i = a
        while i <= b:
            if not v[i]:
                j = i
                while j <= b and not v[j]:
                    j += 1
                if (j - i) * 0.01 >= MINGAP:
                    gaps.append((j - i) * 0.01)
                i = j
            else:
                i += 1
    gaps.sort()
    q = lambda p: gaps[int(len(gaps) * p)]
    print('%-20s 总长 %.1fs 成品 %.0f 语音 %.1fs 峰值 %.3f RMS %.1f 缺 %d' % (
        os.path.basename(d), tot, words / tot * 60, voi, peak, 20 * np.log10(st.median(lev) + 1e-12), miss))
    print('   gap %d median %.2f p25 %.2f p75 %.2f p90 %.2f' % (len(gaps), st.median(gaps), q(.25), q(.75), q(.9)))
