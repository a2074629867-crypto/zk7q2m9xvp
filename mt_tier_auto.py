# -*- coding: utf-8 -*-
"""mt_tier_auto.py —— 用 spaCy 依存分析自动判旁白停顿档位（inner/bound/clause）。

为什么需要自动判档：
- 人工三方只标了 60 条（Kappa 0.841）。要给生产链用、要全库回测，必须能自动判。
- 判据必须是**句法**的，不能是时长的（否则就是用答案推答案）。

核心判据（与人工标注任务书同源）：
1. 停顿落在句末标点（. ? !）之后 → `clause`
2. 否则（逗号处），看**依存弧是否跨越停顿点**：
   - 若跨越弧的依存类型全是「成分内」的（det/amod/nmod/acl/advcl/prep/pobj/
     nsubj/dobj/aux/compound/nummod/poss/case/mark/relcl/xcomp/ccomp…）→ `inner`
   - 若跨越弧里出现「成分间」类型（conj / appos / parataxis / cc / list）→ `bound`
3. 若完全没有弧跨越（两侧各自独立）→ `bound`

为什么用「弧类型」而不是「两词是否有直接依存」：
- 并列结构里 `answers` 的 head 是左边的 `expressions`，形式上与「修饰语挂在中心词上」
  完全一样（都是 head 在左、依存项在右）。唯一区别是 dep_ 标签。
- 实测 Q009（expressions, answers）人工判 bound，直接依存判据会误判成 inner。

用法：
  python mt_tier_auto.py                 # 全库判档 + 与人工 60 条比对
  python mt_tier_auto.py --dump out.json # 输出全库判档结果
"""
import argparse
import collections
import json
import sys

sys.path.insert(0, 'D:/py_libs')

import numpy as np  # noqa: E402

WORDS = r'G:/_setup/_matt_asr_words.json'
MINED = r'G:/_setup/matt_pause_mined.json'
ANNOT = r'G:/_setup/_matt_annot2_samples.json'
AFILES = {
    'main': r'G:/_setup/_annot2_matt_main.json',
    'hy4': r'G:/_setup/_annot2_matt_hy4.json',
    'ds': r'G:/_setup/_annot2_matt_ds.json',
}

# 成分内（切开后句子骨架残缺）
INNER_DEPS = {
    'det', 'amod', 'advmod', 'nmod', 'acl', 'relcl', 'advcl', 'prep', 'pobj',
    'nsubj', 'nsubjpass', 'dobj', 'iobj', 'aux', 'auxpass', 'compound',
    'nummod', 'poss', 'case', 'mark', 'xcomp', 'ccomp', 'attr', 'acomp',
    'npadvmod', 'neg', 'quantmod', 'predet', 'expl', 'dative', 'oprd',
}
# 成分间（切开后是两个并列/独立成分）
BOUND_DEPS = {'conj', 'appos', 'parataxis', 'cc', 'list', 'dep'}


def load_words():
    d = json.load(open(WORDS, encoding='utf-8'))
    out = [dict(t0=float(a), t1=float(b), w=w) for a, b, w in d]
    out = [x for x in out if x['t1'] - x['t0'] <= 1.5]
    out.sort(key=lambda r: r['t0'])
    return out


def build_docs(nlp, words):
    """把词拼成文本 → 按句末标点切句 → 每句 spaCy parse。
    返回 (per_word_sent_id, per_word_token_index, docs)。"""
    # 拼文本并记录每个词的字符区间
    parts, spans, pos = [], [], 0
    for w in words:
        parts.append(w['w'])
        spans.append((pos, pos + len(w['w'])))
        pos += len(w['w']) + 1
    text = ' '.join(parts)

    # 按句末标点切句（在词层面切，保证句子边界与词边界一致）
    sent_of_word = [0] * len(words)
    sid = 0
    for i, w in enumerate(words):
        sent_of_word[i] = sid
        if w['w'].rstrip('"\')')[-1:] in '.?!':
            sid += 1

    docs = {}
    for s in range(sid + 1):
        idx = [i for i in range(len(words)) if sent_of_word[i] == s]
        if not idx:
            continue
        a, b = spans[idx[0]][0], spans[idx[-1]][1]
        docs[s] = (nlp(text[a:b]), idx, a)

    # token → word 映射
    tok2word = {}
    for s, (doc, idx, base) in docs.items():
        for t in doc:
            cs = base + t.idx
            for j, wi in enumerate(idx):
                lo, hi = spans[wi]
                if lo <= cs < hi:
                    tok2word[(s, t.i)] = wi
                    break
    return sent_of_word, tok2word, docs


def judge_pause(doc, base, tok2word, wi_left, wi_right):
    """判一处停顿（在 wi_left 与 wi_right 之间）。"""
    # 找左右两侧最近的 token
    left_tok = None
    right_tok = None
    for t in doc:
        w = tok2word.get(t.i)
        if w is None:
            continue
        if w == wi_left:
            left_tok = t
        if w == wi_right and right_tok is None:
            right_tok = t
    if left_tok is None or right_tok is None:
        return None, 'token 映射失败'

    # 句末？
    for t in doc[left_tok.i:right_tok.i]:
        if t.text in ('.', '?', '!'):
            return 'clause', '句末标点 %s' % t.text

    # 跨越弧：head 在左、token 在右（或反之）
    li, ri = left_tok.i, right_tok.i
    crossed = []
    for t in doc:
        h = t.head.i
        if (h <= li and t.i >= ri) or (t.i <= li and h >= ri):
            if t.dep_ != 'punct':
                crossed.append(t.dep_)
    if not crossed:
        return 'bound', '无跨越弧，两侧独立'
    bad = [d for d in crossed if d in BOUND_DEPS]
    if bad:
        return 'bound', '跨越弧含 %s' % '/'.join(sorted(set(bad)))
    unknown = [d for d in crossed if d not in INNER_DEPS]
    if unknown:
        return 'bound', '跨越弧含未知类型 %s' % '/'.join(sorted(set(unknown)))
    return 'inner', '跨越弧全为成分内(%s)' % '/'.join(sorted(set(crossed))[:3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', default=None)
    a = ap.parse_args()

    import spacy
    nlp = spacy.load('en_core_web_sm')

    words = load_words()
    recs = sorted(json.load(open(MINED, encoding='utf-8'))['recs'], key=lambda r: r['s'])
    print('词 %d，停顿 %d' % (len(words), len(recs)))

    sent_of_word, tok2word, docs = build_docs(nlp, words)
    print('句数 %d' % len(docs))

    # 停顿 → 左右词序号（用词中点对齐，与标注导出一致）
    t0s = np.array([w['t0'] for w in words])
    t1s = np.array([w['t1'] for w in words])
    mids = (t0s + t1s) / 2.0

    out = []
    for r in recs:
        mid = (r['s'] + r['e']) / 2.0
        ip = int(np.searchsorted(mids, mid, side='left') - 1)
        inx = int(np.searchsorted(mids, mid, side='left'))
        if ip < 0 or inx >= len(words):
            continue
        s = sent_of_word[ip]
        if s != sent_of_word[inx] or s not in docs:
            out.append(dict(gap=r['gap'], tier='clause', why='跨句', left=words[ip]['w']))
            continue
        doc, idx, base = docs[s]
        # 该句的 token→word 映射是全局 key (s, t.i)，这里要局部化
        local = {t.i: tok2word.get((s, t.i)) for t in doc}
        tier, why = judge_pause_local(doc, local, ip, inx)
        out.append(dict(gap=r['gap'], tier=tier, why=why,
                        left=words[ip]['w'], right=words[inx]['w']))

    ok = [o for o in out if o['tier']]
    print('判档成功 %d / %d' % (len(ok), len(out)))
    print('分布: %s' % dict(collections.Counter(o['tier'] for o in ok)))
    print('\n各档时长:')
    for t in ['inner', 'bound', 'clause']:
        g = np.array([o['gap'] for o in ok if o['tier'] == t])
        if len(g):
            print('  %-7s n=%3d  p25=%.2f  p50=%.2f  p75=%.2f' % (
                t, len(g), np.percentile(g, 25), np.median(g), np.percentile(g, 75)))

    # ---- 与人工 60 条比对
    samples = json.load(open(ANNOT, encoding='utf-8'))
    ann = {n: {k: v['kind'] for k, v in json.load(open(p, encoding='utf-8')).items()}
           for n, p in AFILES.items()}
    # 样本按 gap 贪心匹配回 out
    used, hit = set(), []
    for sm in samples:
        g = sm['_gap']
        best, bd = -1, 1e9
        for i, o in enumerate(out):
            if i in used:
                continue
            d = abs(o['gap'] - g)
            if d < bd:
                bd, best = d, i
        if best >= 0 and bd < 0.02:
            used.add(best)
            gold = [ann[n][sm['key']] for n in ann]
            major = collections.Counter(gold).most_common(1)[0][0]
            hit.append((sm['key'], major, out[best]['tier'], out[best]['why'], g))
    print('\n=== 自动判档 vs 人工多数票（%d 条）===' % len(hit))
    agree = sum(1 for h in hit if h[1] == h[2])
    print('一致 %d / %d = %.1f%%' % (agree, len(hit), 100.0 * agree / len(hit)))
    cm = collections.Counter((h[1], h[2]) for h in hit)
    print('\n混淆（人工→自动）:')
    for k, v in sorted(cm.items(), key=lambda x: -x[1]):
        print('  %-8s → %-8s  %d' % (k[0], k[1], v))
    print('\n不一致明细:')
    for h in hit:
        if h[1] != h[2]:
            print('  %s gap=%.2f 人工=%s 自动=%s | %s' % (h[0], h[4], h[1], h[2], h[3][:50]))

    if a.dump:
        json.dump(out, open(a.dump, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\n全库判档 → %s' % a.dump)


def judge_pause_local(doc, local, wi_left, wi_right):
    """local: token.i → word index（本句内）。"""
    left_tok = right_tok = None
    for t in doc:
        w = local.get(t.i)
        if w is None:
            continue
        if w == wi_left:
            left_tok = t
        if w == wi_right and right_tok is None:
            right_tok = t
    if left_tok is None or right_tok is None:
        return None, 'token 映射失败'

    for t in doc[left_tok.i:right_tok.i]:
        if t.text in ('.', '?', '!'):
            return 'clause', '句末 %s' % t.text

    li, ri = left_tok.i, right_tok.i
    crossed = []
    for t in doc:
        h = t.head.i
        if (h <= li and t.i >= ri) or (t.i <= li and h >= ri):
            if t.dep_ != 'punct':
                crossed.append(t.dep_)
    if not crossed:
        return 'bound', '无跨越弧'
    bad = sorted(set(d for d in crossed if d in BOUND_DEPS))
    if bad:
        return 'bound', '跨弧含 %s' % '/'.join(bad)
    unknown = sorted(set(d for d in crossed if d not in INNER_DEPS))
    if unknown:
        return 'bound', '跨弧未知 %s' % '/'.join(unknown)
    return 'inner', '跨弧成分内 %s' % '/'.join(sorted(set(crossed))[:3])


if __name__ == '__main__':
    main()
