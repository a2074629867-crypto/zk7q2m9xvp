# -*- coding: utf-8 -*-
"""
旁白韵律闸 v2 —— 帧级找峰 → 映射到词 → 判三条位置律。

关键：峰必须在**音频帧级**找（人耳听的是连续曲线），再用词时间戳 t0/t1 映射到词。
      词级 f0_med_rel 的局部最大太稀疏（实测密度只有真人的 2%），不能用来判 P1/P3。

检测器与人类参考完全同一套参数（prom_st=2.0, min_gap=0.20s, 平滑 7 帧=70ms），保证可比。

P1 峰只落内容词      (Selkirk 1984; Ladd 1996; Beckman & Hirschberg 1994)
P2 末峰在最右实词    (Chomsky & Halle 1968; Liberman & Prince 1977)
P3 峰密度 ≈ 人类     (实测 159 条人类参考 = 0.34 峰/秒; 峰数中位 2 vs 我们 4/3)
"""
import json, re, sys, csv, os
import numpy as np
import spacy

DOC = 'G:/_setup'
CONTENT = {'NOUN', 'VERB', 'ADJ', 'PROPN'}
FUNC = {'DET', 'ADP', 'PRON', 'AUX', 'CCONJ', 'SCONJ', 'PART', 'INTJ', 'NUM'}
ABBR = {'Mr', 'Mrs', 'Dr', 'St', 'Jr', 'Sr', 'Prof'}

import soundfile as sf
import parselmouth


def audio_peaks(path, prom_st=2.0, min_gap=0.20, smooth=3):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1:
        y = y.mean(1)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=350)
    f0 = p.selected_array['frequency'].astype(float)
    v = f0 > 0
    if v.sum() < 40:
        return None
    st = np.where(v, 12 * np.log2(np.maximum(f0, 1) / 100.0), np.nan)
    s = st.copy()
    for i in range(smooth, len(s) - smooth):
        w = s[i - smooth:i + smooth + 1]
        w = w[~np.isnan(w)]
        if len(w):
            s[i] = np.median(w)
    nvoiced = int((~np.isnan(s)).sum())
    if nvoiced < 30:
        return None
    # 把 NaN 用线性插值填满，保证索引 === 0.01s 时间轴
    idx = np.arange(len(s))
    good = ~np.isnan(s)
    vals = np.interp(idx, idx[good], s[good])
    w = int(min_gap / 2 / 0.01)          # ±w 帧 ⇒ 最小峰间隔 = min_gap
    out = []
    for k in range(w, len(vals) - w):
        if vals[k] != vals[k - w:k + w + 1].max():
            continue
        L = vals[max(0, k - 30):k + 1].min()
        R = vals[k:min(len(vals), k + 31)].min()
        pr = vals[k] - max(L, R)
        if pr >= prom_st and good[k]:     # 峰必须落在有声帧上
            out.append((float(k * 0.01), float(vals[k]), float(pr)))
    # 强制最小间隔：按突出度从大到小贪心保留（避免平顶重复计数）
    out.sort(key=lambda x: -x[2])
    kept = []
    for t, h, pr in out:
        if all(abs(t - t2) >= min_gap for t2, _, _ in kept):
            kept.append((t, h, pr))
    kept.sort()
    return kept, len(y) / sr


def align(tts_words, doc):
    toks = [t for t in doc if not t.is_punct]
    merged = []
    k = 0
    w = list(tts_words)
    while k < len(w):
        cur = w[k]
        if (k + 1 < len(w) and w[k + 1] == '.' and re.fullmatch(r"[A-Z][a-z]{0,3}", cur or "")
                and (cur in ABBR or len(cur) == 1)):
            merged.append((k, cur + '.'))
            k += 2
        else:
            merged.append((k, cur))
            k += 1
    merged = [(oi, t) for oi, t in merged if t and not re.fullmatch(r"[.,;:!?\"'—-]+", t)]
    if len(merged) != len(toks):
        return None
    return [(oi, tk) for (oi, _), tk in zip(merged, toks)]


def map_peak(t, words):
    """峰时刻 → 词索引（落在哪个词的时间区间；落在间隙则归到最近的词）"""
    best, bd = None, 1e9
    for i, w in enumerate(words):
        t0, t1 = w.get('t0', 0), w.get('t1', 0)
        if t0 <= t <= t1:
            return i
        d = min(abs(t - t0), abs(t - t1))
        if d < bd:
            bd, best = d, i
    return best


def main(vers=('old', 'new'), limit=None):
    nlp = spacy.load('en_core_web_sm')
    P = json.load(open(f'{DOC}/_prosody5_all.json', encoding='utf-8'))
    W = json.load(open(f'{DOC}/_wl_final2.json', encoding='utf-8'))
    texts = {k.rsplit('/', 1)[-1]: v['text'] for k, v in W.items()}
    roots = {'old': f'{DOC}/_audio_ch123/out', 'new': f'{DOC}/_regen_final'}

    ids = sorted(texts)
    if limit:
        ids = ids[:limit]
    rows, fail, missing = [], 0, 0
    for n, sid in enumerate(ids, 1):
        doc = nlp(texts[sid])
        for ver in vers:
            r = P.get(f'{sid}|{ver}')
            wav = f'{roots[ver]}/{sid}.wav'
            if not r or not os.path.exists(wav):
                missing += 1
                continue
            words = r['words']
            al = align([w['w'] for w in words], doc)
            if al is None:
                fail += 1
                continue
            pos = {oi: tk.pos_ for oi, tk in al}
            ap = audio_peaks(wav)
            if not ap:
                fail += 1
                continue
            pk, dur = ap
            idxs = [(map_peak(t, words), h, pr) for t, h, pr in pk]
            idxs = [(i, h, pr) for i, h, pr in idxs if i is not None and i in pos]
            if not idxs:
                continue
            # P1
            bad = [i for i, _, _ in idxs if pos.get(i) in FUNC]
            top_i = max(idxs, key=lambda x: x[1])[0]
            # P2
            cont = [i for i in pos if pos[i] in CONTENT]
            last_pk = max(i for i, _, _ in idxs)
            last_cont = max(cont) if cont else None
            p2_ok = (last_pk == last_cont) if last_cont is not None else None
            tail = sum(1 for i in cont if i > last_pk) if cont else -1
            flags = []
            if bad:
                flags.append(f'P1x{len(bad)}')
            if p2_ok is False:
                flags.append(f'P2(follow{tail})')
            rows.append(dict(
                sid=sid, ver=ver, nw=len(words), dur=round(dur, 2),
                n_peak=len(idxs), dens=round(len(idxs) / max(dur, 0.1), 2),
                p1_bad=len(bad), p1_rate=round(len(bad) / len(idxs) * 100, 1),
                top_w=words[top_i]['w'], top_pos=pos.get(top_i, '?'),
                top_func=pos.get(top_i) in FUNC,
                last_pk_w=words[last_pk]['w'], last_cont_w=words[last_cont]['w'] if last_cont is not None else '',
                p2_ok=p2_ok, p2_tail=tail,
                p3_ratio=round(len(idxs) / max(dur, 0.1) / 0.34, 2),
                flags=' '.join(flags),
            ))
        if n % 100 == 0:
            print(f'  ...{n}/{len(ids)}', flush=True)
    print(f'判定 {len(rows)} 条句-版本；对齐/读取失败 {fail}；缺文件 {missing}')

    with open(f'{DOC}/_gate_pos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(rows, open(f'{DOC}/_gate_pos.json', 'w', encoding='utf-8'), ensure_ascii=False)

    print(f'\n{"指标":<32}{"old":>10}{"new":>10}{"通过线":>9}')
    for k, name, fmt in (('p1_top_func', 'P1 最大峰落功能词', '{:.1f}%'),
                         ('p2_bad', 'P2 末峰不是最右实词', '{:.1f}%'),
                         ('p3_med', 'P3 峰密度 / 人类(0.34/s)', '{:.2f}x'),
                         ('p1_rate', '辅助：峰落功能词占全部峰', '{:.1f}%')):
        line = f'  {name:<30}'
        for ver in vers:
            sub = [r for r in rows if r['ver'] == ver]
            if k == 'p1_top_func':
                val = np.mean([r['top_func'] for r in sub]) * 100
            elif k == 'p2_bad':
                val = np.mean([r['p2_ok'] is False for r in sub]) * 100
            elif k == 'p3_med':
                val = np.median([r['p3_ratio'] for r in sub])
            else:
                val = np.mean([r['p1_rate'] for r in sub])
            line += f'{fmt.format(val):>10}'
        print(line)
    print(f'  {"目标":<30}{"P1<10%":>10}{"P2<20%":>10}{"P3<=1.2x":>10}')

    worst = sorted([r for r in rows if r['top_func'] and r['p2_ok'] is False],
                   key=lambda r: -(r['p1_bad'] * 3 + max(r['p2_tail'], 0)))
    print(f'\n=== P1+P2 同时违规 {len(worst)} 条，最严重 10 条：')
    for r in worst[:10]:
        print(f"  {r['sid']} {r['ver']:4s} 峰{r['n_peak']:2d} 密度{r['p3_ratio']:.2f}x "
              f"最大峰={r['top_w']}({r['top_pos']}) 末峰={r['last_pk_w']} 应为{r['last_cont_w']} 后{r['p2_tail']}实词")
    print(f'\n→ _gate_pos.csv / _gate_pos.json')


if __name__ == '__main__':
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit=lim)
