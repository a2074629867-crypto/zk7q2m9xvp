# -*- coding: utf-8 -*-
"""
测「起伏落在错误的词」—— 位置判据，不看音高区间。

用户 2026-11-25 04:0x 的纠正：
  「音高区间完全不是问题……问题是起伏落在错误的词、错误的地方，用了错误的停顿。」

所以这里不测 span（幅度），只测**分配**：

  A. 峰的词性           —— 英语 pitch accent 默认只落在内容词上（Selkirk 1984 / Ladd 1996）
  B. 句末焦点（NSR）     —— 最后一个峰应落在最右的实词上，其后是低平 tail
                          （Chomsky & Halle 1968 重音规则；Liberman & Prince 1977）
  C. 峰与 LLM 期望词     —— 分类统计，不只看命中率

可用性门槛沿用 §16.7：dur≥0.12s 且 有声帧≥5。
"""
import json, re, sys
import numpy as np
import spacy

DOC = 'G:/_setup'
CONTENT = {'NOUN', 'VERB', 'ADJ', 'PROPN'}      # 核心内容词
FUNC = {'DET', 'ADP', 'PRON', 'AUX', 'CCONJ', 'SCONJ', 'PART', 'INTJ', 'NUM'}
ABBR = {'Mr', 'Mrs', 'Dr', 'St', 'Jr', 'Sr', 'Prof', 'M', 'J', 'T', 'S', 'D', 'A', 'E', 'H'}


def align(tts_words, doc):
    """把 TTS 词表（标点独立成 token）对齐到 spaCy token。返回 [(idx_in_tts, spacy_tok)]"""
    toks = [t for t in doc if not t.is_punct]
    out = []
    i = 0
    ti = 0
    w = list(tts_words)
    # 先合并缩写：'Mrs' + '.' → 一个词
    merged = []
    k = 0
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


def peaks_of(words, min_i=1):
    """返回 [(idx, height, word, pos)]，height = 2*m[i]-m[i-1]-m[i+1]"""
    m = [w.get('f0_med_rel') for w in words]
    out = []
    for i in range(min_i, len(m) - 1):
        if None in (m[i - 1], m[i], m[i + 1]):
            continue
        ok = all(w.get('dur', 0) >= 0.12 and w.get('voiced_ratio', 0) * (w.get('dur', 0) / 0.01) >= 5
                 for w in (words[i - 1], words[i], words[i + 1]))
        if not ok:
            continue
        out.append((i, 2 * m[i] - m[i - 1] - m[i + 1]))
    return out


def main():
    nlp = spacy.load('en_core_web_sm')
    P = json.load(open(f'{DOC}/_prosody5_all.json', encoding='utf-8'))
    W = json.load(open(f'{DOC}/_wl_final2.json', encoding='utf-8'))
    L = json.load(open(f'{DOC}/_cells_llm.json', encoding='utf-8'))
    texts = {k.rsplit('/', 1)[-1]: v['text'] for k, v in W.items()}

    rows = []
    skipped = 0
    for sid in sorted(texts):
        doc = nlp(texts[sid])
        for ver in ('old', 'new'):
            r = P.get(f'{sid}|{ver}')
            if not r:
                continue
            words = r['words']
            tts = [w['w'] for w in words]
            al = align(tts, doc)
            if al is None:
                skipped += 1
                continue
            pos = {}
            for oi, tk in al:
                pos[oi] = (tk.pos_, tk.tag_, tk.lemma_.lower())
            pk = peaks_of(words)
            if not pk:
                continue
            # 只保留有词性标注的峰
            pk = [(i, h) for i, h in pk if i in pos]
            if not pk:
                continue
            pk.sort(key=lambda x: -x[1])
            top_i, top_h = pk[0]
            last_i, last_h = max(pk, key=lambda x: x[0])
            # 句子最后一个内容词的位置
            cont_idx = [i for i in pos if pos[i][0] in CONTENT]
            last_cont = max(cont_idx) if cont_idx else None
            # 最后一个峰之后还有几个内容词
            tail_cont = sum(1 for i in cont_idx if i > last_i)
            prom = [x.lower() for x in str(L.get(sid, {}).get('prom', '')).split('|') if x.strip()]
            rows.append(dict(
                sid=sid, ver=ver, nw=len(words),
                top_w=words[top_i]['w'], top_pos=pos[top_i][0], top_lemma=pos[top_i][2],
                top_h=round(top_h, 1), top_rel=round(top_i / max(len(words) - 1, 1), 2),
                top_is_content=pos[top_i][0] in CONTENT,
                top_is_func=pos[top_i][0] in FUNC,
                n_peaks=len(pk),
                last_pos=pos[last_i][0], last_rel=round(last_i / max(len(words) - 1, 1), 2),
                tail_cont=tail_cont,
                last_is_last_cont=(last_i == last_cont),
                hit_prom=words[top_i]['w'].lower().strip('.,;:!?') in prom,
            ))
    print(f'可用 {len(rows)} 条句-版本，对齐失败 {skipped} 次')
    json.dump(rows, open(f'{DOC}/_pos_accent.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    def agg(ver):
        sub = [r for r in rows if r['ver'] == ver]
        n = len(sub)
        return dict(
            n=n,
            top_func=np.mean([r['top_is_func'] for r in sub]) * 100,
            top_content=np.mean([r['top_is_content'] for r in sub]) * 100,
            top_not_content=np.mean([not r['top_is_content'] for r in sub]) * 100,
            last_miss=np.mean([not r['last_is_last_cont'] for r in sub]) * 100,
            tail_ge2=np.mean([r['tail_cont'] >= 2 for r in sub]) * 100,
            hit_prom=np.mean([r['hit_prom'] for r in sub]) * 100,
            peaks_med=float(np.median([r['n_peaks'] for r in sub])),
            top_rel_med=float(np.median([r['top_rel'] for r in sub])),
        )

    print('\n=== 位置指标（句-版本）')
    hdr = f"{'指标':<26}{'old':>9}{'new':>9}"
    print(hdr)
    o, n = agg('old'), agg('new')
    items = [
        ('最大峰落在功能词', 'top_func', '%'),
        ('最大峰落在内容词', 'top_content', '%'),
        ('最大峰非内容词(=错位)', 'top_not_content', '%'),
        ('末峰不是最右实词(丢NSR)', 'last_miss', '%'),
        ('末峰后≥2个实词(长tail)', 'tail_ge2', '%'),
        ('最大峰命中LLM期望词', 'hit_prom', '%'),
        ('峰数中位', 'peaks_med', ''),
        ('最大峰相对位置中位', 'top_rel_med', ''),
    ]
    for name, k, u in items:
        print(f'{name:<26}{o[k]:>9.1f}{n[k]:>9.1f}{u}')
    print(f"{'可用句数':<26}{o['n']:>9d}{n['n']:>9d}")

    print('\n=== 最大峰词性分布（top-8）')
    for ver in ('old', 'new'):
        sub = [r for r in rows if r['ver'] == ver]
        from collections import Counter
        c = Counter(r['top_pos'] for r in sub)
        tot = len(sub)
        print(f'  {ver}: ' + '  '.join(f'{k} {v/tot*100:.0f}%' for k, v in c.most_common(8)))

    print('\n=== c2_0191 / c1_0061 / c1_0048 明细')
    for sid in ('c2_0191', 'c1_0061', 'c1_0048'):
        for ver in ('old', 'new'):
            r = next((x for x in rows if x['sid'] == sid and x['ver'] == ver), None)
            if r:
                print(f"  {sid} {ver:4s} 最大峰={r['top_w']}({r['top_pos']},{r['top_h']:+.1f}st,@ {r['top_rel']:.2f}) "
                      f"末峰词性={r['last_pos']} 末峰后实词={r['tail_cont']} 命中期望={r['hit_prom']}")


if __name__ == '__main__':
    main()
