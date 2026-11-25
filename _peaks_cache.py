# -*- coding: utf-8 -*-
"""
峰缓存 + 判据重算（P1 / P2 / P3）。

为什么要有这一层：
  1) 峰检测要走音频（parselmouth），慢；判据（P1/P2/P3）只是几何，应该能一秒重算。
  2) 上一版 P2 的定义被 P1 污染了 —— 末峰落在功能词上时，「末峰 != 最右实词」必然成立，
     于是 P2 数字里混着一堆 P1 的违规。本脚本把 P2 改成**条件口径**：
     只在「落在内容词上的峰」里取最右那个，看它是不是最右内容词。
  3) P1 增加**窄焦点豁免**：LLM 标了 `focus=窄焦点` 且该功能词正是被标为焦点的词时，允许它带峰
     （对比焦点可以把重音放在功能词上，这是 ToBI 里就有的情形）。豁免必须可审计，所以单独计数。

产物：_peaks_cache.json（每条句-版本的峰表 + 词性）、_gate2.json / _gate2.csv（重算后的判定）
"""
import json, os, sys, csv
import numpy as np
import spacy
from multiprocessing import Pool

DOC = 'G:/_setup'
sys.path.insert(0, DOC)
from _gate_pos import audio_peaks, map_peak, align, CONTENT, FUNC  # 同一检测器，不许另起口径

ROOTS = {'old': f'{DOC}/_audio_ch123/out', 'new': f'{DOC}/_regen_final'}
CACHE = f'{DOC}/_peaks_cache.json'


def job(arg):
    sid, ver = arg
    p = f'{ROOTS[ver]}/{sid}.wav'
    if not os.path.exists(p):
        return sid, ver, None
    ap = audio_peaks(p)
    if not ap:
        return sid, ver, None
    pk, dur = ap
    return sid, ver, {'dur': round(dur, 3), 'peaks': [[round(t, 3), round(h, 2), round(pr, 2)] for t, h, pr in pk]}


def build_cache(vers=('old', 'new')):
    P = json.load(open(f'{DOC}/_prosody5_all.json', encoding='utf-8'))
    ids = sorted({k.split('|')[0] for k in P})
    tasks = [(s, v) for s in ids for v in vers]
    print(f'需要分析 {len(tasks)} 条音频', flush=True)
    out = {}
    with Pool(6) as pool:
        for n, (sid, ver, r) in enumerate(pool.imap_unordered(job, tasks, chunksize=8), 1):
            if r:
                out[f'{sid}|{ver}'] = r
            if n % 200 == 0:
                print(f'  ...{n}/{len(tasks)}', flush=True)
    json.dump(out, open(CACHE, 'w', encoding='utf-8'))
    print(f'写入 {CACHE}：{len(out)} 条', flush=True)
    return out


def score():
    C = json.load(open(CACHE, encoding='utf-8'))
    P = json.load(open(f'{DOC}/_prosody5_all.json', encoding='utf-8'))
    W = json.load(open(f'{DOC}/_wl_final2.json', encoding='utf-8'))
    L = json.load(open(f'{DOC}/_cells_llm.json', encoding='utf-8'))
    texts = {k.rsplit('/', 1)[-1]: v['text'] for k, v in W.items()}
    nlp = spacy.load('en_core_web_sm')
    base = json.load(open(f'{DOC}/_dens_base.json', encoding='utf-8'))['human']

    rows = []
    for sid in sorted(texts):
        doc = nlp(texts[sid])
        lab = L.get(sid, {})
        focus_narrow = lab.get('focus') == '窄焦点'
        prom = {x.strip().lower() for x in str(lab.get('prom', '')).split('|') if x.strip()}
        for ver in ('old', 'new'):
            c = C.get(f'{sid}|{ver}')
            r = P.get(f'{sid}|{ver}')
            if not c or not r:
                continue
            words = r['words']
            al = align([w['w'] for w in words], doc)
            if al is None:
                continue
            pos = {oi: tk.pos_ for oi, tk in al}
            idxs = []
            for t, h, pr in c['peaks']:
                i = map_peak(t, words)
                if i is None or i not in pos:
                    continue
                idxs.append((i, h, pr))
            if not idxs:
                continue

            # ---- P1：峰落在功能词上（窄焦点豁免）----
            bad, exempt = [], []
            for i, h, pr in idxs:
                if pos.get(i) in FUNC:
                    wl = words[i]['w'].lower().strip('.,;:!?\"\'')
                    if focus_narrow and wl in prom:
                        exempt.append(i)
                    else:
                        bad.append(i)
            top_i, top_h, _ = max(idxs, key=lambda x: x[1])

            # ---- P2：条件口径，只在内容词峰里取最右 ----
            cont = sorted(i for i in pos if pos[i] in CONTENT)
            cont_pk = [i for i, _, _ in idxs if pos.get(i) in CONTENT]
            last_cont = cont[-1] if cont else None
            last_cont_pk = max(cont_pk) if cont_pk else None
            p2_ok = (last_cont_pk == last_cont) if (last_cont is not None and last_cont_pk is not None) else None
            tail = (len([i for i in cont if i > last_cont_pk]) if last_cont_pk is not None else -1)
            # 辅助：末峰本身是不是内容词（这才是被 P1 污染的那个数）
            last_pk_is_cont = pos.get(max(i for i, _, _ in idxs)) in CONTENT

            rows.append(dict(
                sid=sid, ver=ver, nw=len(words), dur=c['dur'],
                n_peak=len(idxs), dens=round(len(idxs) / max(c['dur'], 0.1), 3),
                p3_ratio=round(len(idxs) / max(c['dur'], 0.1) / base, 2),
                p1_bad=len(bad), p1_exempt=len(exempt),
                p1_rate=round(len(bad) / len(idxs) * 100, 1),
                top_w=words[top_i]['w'], top_pos=pos.get(top_i, '?'),
                top_func=pos.get(top_i) in FUNC,
                p2_ok=p2_ok, p2_tail=tail,
                last_pk_is_cont=last_pk_is_cont,
                last_pk_w=words[max(i for i, _, _ in idxs)]['w'],
                last_cont_w=words[last_cont]['w'] if last_cont is not None else '',
                n_cont=len(cont),
            ))

    json.dump(rows, open(f'{DOC}/_gate2.json', 'w', encoding='utf-8'), ensure_ascii=False)
    with open(f'{DOC}/_gate2.csv', 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    print(f'\n判定 {len(rows)} 条句-版本（人类峰密度基线 {base:.2f}/s）\n')
    print(f'{"指标":<34}{"旧版":>10}{"新版":>10}{"通过线":>10}')
    for ver in ('old', 'new'):
        pass
    def g(ver, fn):
        sub = [r for r in rows if r['ver'] == ver]
        return fn(sub)
    metrics = [
        ('P1 最大峰落功能词', lambda s: np.mean([r['top_func'] for r in s]) * 100, '<10%', '{:.1f}%'),
        ('P1 任一峰落功能词（句占比）', lambda s: np.mean([r['p1_bad'] > 0 for r in s]) * 100, '—', '{:.1f}%'),
        ('P2 末峰不是最右实词（条件口径）', lambda s: np.mean([r['p2_ok'] is False for r in s]) * 100, '<20%', '{:.1f}%'),
        ('P3 峰密度 / 人类', lambda s: float(np.median([r['p3_ratio'] for r in s])), '<=1.5x', '{:.2f}x'),
    ]
    for name, fn, tgt, fmt in metrics:
        print(f'  {name:<32}{fmt.format(g("old", fn)):>10}{fmt.format(g("new", fn)):>10}{tgt:>10}')

    print()
    for ver in ('old', 'new'):
        s = [r for r in rows if r['ver'] == ver]
        p1 = [r for r in s if r['top_func']]
        p2 = [r for r in s if r['p2_ok'] is False]
        p3 = [r for r in s if r['p3_ratio'] > 1.5]
        clean = [r for r in s if not r['top_func'] and r['p2_ok'] is not False and r['p3_ratio'] <= 1.5]
        ex = sum(r['p1_exempt'] for r in s)
        print(f'{ver}: n={len(s)}  P1违规 {len(p1)} ({len(p1)/len(s)*100:.1f}%)  '
              f'P2违规 {len(p2)} ({len(p2)/len(s)*100:.1f}%)  P3违规 {len(p3)} ({len(p3)/len(s)*100:.1f}%)  '
              f'**三律全过 {len(clean)} ({len(clean)/len(s)*100:.1f}%)**  窄焦点豁免峰 {ex}')
    print()
    print('=== 末峰本身是否内容词（旧口径被 P1 污染的程度）')
    for ver in ('old', 'new'):
        s = [r for r in rows if r['ver'] == ver]
        print(f'  {ver}: 末峰是内容词 {np.mean([r["last_pk_is_cont"] for r in s])*100:.1f}%')


if __name__ == '__main__':
    if '--score' in sys.argv:
        score()
    else:
        build_cache()
        score()
