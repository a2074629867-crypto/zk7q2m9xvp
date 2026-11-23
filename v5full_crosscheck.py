# -*- coding: utf-8 -*-
"""v5full_crosscheck.py —— 双模型交叉验证

两个独立模型（large-v3-turbo vs small.en）都认同 → 高置信；
分歧处 → 错词嫌疑点，交给人工复核。

做法
----
① small.en 只有 segment 级时间戳 → 把每个 segment 的词沿时间轴线性铺开，得到近似词时间戳
② 两个模型的词流各自按「词中点归属」分配到切片
③ 逐片做 difflib 序列比对 → 分歧点 + 分歧率
④ 全局比对 → 整体一致率
"""
import argparse, difflib, json, os, re
from collections import Counter

STOP = set('the a an and or but of to in on at for with is was were are be been am it he she they we you i his her their its my our your this that these those as by from not no so if then than there here when while'.split())


def norm(w):
    w = re.sub(r"[^A-Za-z0-9']", '', w).lower()
    return w


def seg_words(segs):
    """segment 级 → 近似词级（线性铺开）"""
    out = []
    for s in segs:
        toks = s['text'].split()
        if not toks:
            continue
        span = max(0.01, s['end'] - s['start'])
        n = len(toks)
        for k, t in enumerate(toks):
            out.append((s['start'] + span * k / n, s['start'] + span * (k + 1) / n, t))
    return out


def assign(slices, words):
    """词中点归属到切片"""
    rows = [[] for _ in slices]
    idx = 0
    for (a, b, w) in words:
        mid = (a + b) / 2
        while idx < len(slices) - 1 and mid > slices[idx]['t1']:
            idx += 1
        while idx > 0 and mid < slices[idx]['t0']:
            idx -= 1
        rows[idx].append(w)
    return [' '.join(r).strip() for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--turbo', required=True, help='large-v3-turbo 分块输出 json')
    ap.add_argument('--small', required=True, help='small.en 整段输出 json（含 segments）')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    T = json.load(open(args.turbo, encoding='utf-8'))
    S = json.load(open(args.small, encoding='utf-8'))
    sl = sorted(T['slices'], key=lambda s: s['t0'])

    t_txt = [s['text'] for s in sl]
    sw = seg_words(S['segments'])
    s_txt = assign(sl, sw)

    print('切片 %d 条 | turbo 词 %d | small.en 词 %d'
          % (len(sl), sum(len(t.split()) for t in t_txt), sum(len(t.split()) for t in s_txt)))

    # ---- 全局一致率 ----
    A = [norm(w) for w in ' '.join(t_txt).split()]
    B = [norm(w) for w in ' '.join(s_txt).split()]
    A = [w for w in A if w]; B = [w for w in B if w]
    sm = difflib.SequenceMatcher(None, A, B)
    agree = sum(bl.size for bl in sm.get_matching_blocks())
    print('\n=== 全局 ===')
    print('  turbo %d 词 | small.en %d 词 | 一致 %d (%.1f%%)'
          % (len(A), len(B), agree, 100 * agree / max(1, len(A))))

    # ---- 逐片比对 ----
    out_slices, stat = [], Counter()
    for i, s in enumerate(sl):
        a = [norm(w) for w in t_txt[i].split()]
        b = [norm(w) for w in s_txt[i].split()]
        a = [w for w in a if w]; b = [w for w in b if w]
        m = difflib.SequenceMatcher(None, a, b)
        ok = sum(bl.size for bl in m.get_matching_blocks())
        n = max(len(a), len(b))
        rate = ok / n if n else 1.0
        diffs = []
        for tag, i1, i2, j1, j2 in m.get_opcodes():
            if tag == 'equal':
                continue
            diffs.append(dict(tag=tag, turbo=' '.join(a[i1:i2]),
                              small=' '.join(b[j1:j2])))
        flags = []
        if n and rate < 0.75:
            flags.append('disagree_big'); stat['disagree_big'] += 1
        elif n and rate < 0.95:
            flags.append('disagree'); stat['disagree'] += 1
        # 关键词（非停用词）分歧
        key = [d for d in diffs
               if any(w not in STOP and len(w) > 2 for w in (d['turbo'] + ' ' + d['small']).split())]
        if key:
            flags.append('key_diff'); stat['key_diff'] += 1
        out_slices.append(dict(i=i, file=s['file'], t0=s['t0'], t1=s['t1'],
                               turbo=t_txt[i], small=s_txt[i],
                               rate=round(rate, 3), diffs=diffs, flags=flags))

    json.dump(dict(turbo_model=T.get('model'), small_model=S.get('model'),
                   n_slices=len(sl), global_agree=round(agree / max(1, len(A)), 4),
                   stat=dict(stat), slices=out_slices),
              open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n=== 逐片分歧统计 ===')
    for k, v in stat.most_common():
        print('  %-16s %d' % (k, v))
    print('\n分歧最大的 15 条：')
    for r in sorted(out_slices, key=lambda x: x['rate'])[:15]:
        print('  [%.2f] %7.2f-%7.2fs' % (r['rate'], r['t0'], r['t1']))
        print('        turbo: %s' % r['turbo'][:100])
        print('        small: %s' % r['small'][:100])
    print('写出 %s' % args.out)
    print('CROSSDONE')


if __name__ == '__main__':
    main()
