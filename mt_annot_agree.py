# -*- coding: utf-8 -*-
"""mt_annot_agree.py —— 三方标注交叉验证。

对齐方式：按 (key, 标点出现顺序 index) 对齐，不按 after 词对齐
（不同标注者可能抄错词形，但标点顺序不会错）。

输出：
  - 三方圆桌（全一致 / 2:1 / 全不一致）
  - Fleiss' Kappa
  - 逐条分歧清单
"""
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

FILES = {
    'main': r'G:/_setup/_annot_main.json',
    'hy4': r'G:/_setup/_annot_hy4.json',
    'ds': r'G:/_setup/_annot_ds.json',
}

TEXTS = {}


def load_texts():
    sys.path.insert(0, r'G:/_setup')
    from ch123_plan import PLAN, INNER
    for i, _, _, t in PLAN:
        TEXTS['L%03d' % i] = t
    for i, (_, _, _, t) in enumerate(INNER):
        TEXTS['I%02d' % i] = t


def n_punct(t):
    """标点个数：只数 , . ? ! ; :（省略号不计，与标注规格一致）"""
    return len(re.findall(r'[,\.\?;:!]', t))


def load(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print('  [FAIL] %s: %s' % (path, e))
        return None
    # 容错：有些模型会多包一层
    if isinstance(d, dict) and len(d) == 1 and isinstance(list(d.values())[0], dict) \
            and 'kind' not in list(d.values())[0]:
        d = list(d.values())[0]
    return d


def fleiss(rows):
    """rows: list of list[label]（每个 item 的 n 个标注）。
    返回 (kappa, P_bar, P_e)"""
    items = [r for r in rows if len(r) >= 2]
    if not items:
        return None, None, None
    cats = sorted(set(l for r in items for l in r))
    idx = {c: i for i, c in enumerate(cats)}
    N = len(items)
    n = len(items[0])
    P = []
    for r in items:
        c = Counter(r)
        s = sum(v * v for v in c.values())
        P.append((s - n) / (n * (n - 1)))
    P_bar = sum(P) / N
    # P_e
    tot = Counter()
    for r in items:
        for l in r:
            tot[l] += 1
    P_e = sum((v / (N * n)) ** 2 for v in tot.values())
    if P_e >= 1:
        return 1.0, P_bar, P_e
    return (P_bar - P_e) / (1 - P_e), P_bar, P_e


def main():
    load_texts()
    ann = {}
    for name, p in FILES.items():
        d = load(p)
        if d is not None:
            ann[name] = d
    if len(ann) < 2:
        print('可用标注者 <2，无法交叉验证')
        return
    names = list(ann)
    print('可用标注者: %s' % ', '.join(names))

    # 覆盖检查
    print('\n=== 覆盖检查 ===')
    keys = sorted(set(k for d in ann.values() for k in d))
    for k in keys:
        exp = n_punct(TEXTS.get(k, ''))
        line = '  %-5s 期望 %d 处 |' % (k, exp)
        for nm in names:
            v = ann[nm].get(k)
            got = len(v['kind']) if v and 'kind' in v else -1
            line += ' %s %d%s' % (nm, got, '' if got == exp else '⚠')
        print(line)

    # 逐处对齐
    print('\n=== 逐处一致性 ===')
    per_item = []          # [(key, idx, [labels])]
    for k in keys:
        exp = n_punct(TEXTS.get(k, ''))
        for i in range(exp):
            labs = []
            for nm in names:
                v = ann[nm].get(k)
                if not v or 'kind' not in v or i >= len(v['kind']):
                    continue
                labs.append(v['kind'][i].get('kind', '?'))
            if len(labs) >= 2:
                per_item.append((k, i, labs))

    full = sum(1 for _, _, l in per_item if len(set(l)) == 1)
    print('  可对齐 %d 处' % len(per_item))
    print('  全一致 %d (%.0f%%)' % (full, 100 * full / max(1, len(per_item))))
    kappa, pb, pe = fleiss([l for _, _, l in per_item])
    if kappa is not None:
        print("  Fleiss' Kappa = %.3f  (P_bar %.3f / P_e %.3f)" % (kappa, pb, pe))
        if kappa >= 0.6:
            print('  → 一致性可接受（≥0.6），可扩到全量')
        elif kappa >= 0.4:
            print('  → 中等一致，需先修判据再扩量')
        else:
            print('  → 一致性不足，判据或样本有问题')

    # 分歧清单
    print('\n=== 分歧清单（全不一致 + 2:1）===')
    for k, i, l in per_item:
        if len(set(l)) == 1:
            continue
        t = TEXTS.get(k, '')
        # 找第 i 个标点前的词
        pos = [m.start() for m in re.finditer(r'[,\.\?;:!]', t)]
        ctx = t[max(0, pos[i] - 22):pos[i] + 2] if i < len(pos) else t[:22]
        tag = '全分歧' if len(set(l)) == 3 else '2:1'
        print('  %-5s #%d %-6s %s | %s' % (k, i, tag, dict(zip(names, l)), ctx))

    # 分 kind 的一致率
    print('\n=== 各 kind 的标注分布 ===')
    for nm in names:
        c = Counter()
        for k in keys:
            v = ann[nm].get(k)
            if v and 'kind' in v:
                for x in v['kind']:
                    c[x.get('kind', '?')] += 1
        print('  %-5s %s' % (nm, dict(c)))

    # sentence_type / focus 一致率
    print('\n=== sentence_type / focus 一致率 ===')
    st_full = sum(1 for k in keys if len(set(
        (ann[nm].get(k) or {}).get('sentence_type', '?') for nm in names)) == 1)
    print('  sentence_type 全一致 %d / %d (%.0f%%)'
          % (st_full, len(keys), 100 * st_full / len(keys)))
    for k in keys:
        vals = [(ann[nm].get(k) or {}).get('sentence_type', '?') for nm in names]
        if len(set(vals)) > 1:
            print('    %-5s %s' % (k, dict(zip(names, vals))))
    print()
    for k in keys:
        vals = [(ann[nm].get(k) or {}).get('focus', '?') for nm in names]
        if len(set(vals)) > 1:
            print('    focus %-5s %s | %s' % (k, dict(zip(names, vals)),
                                              TEXTS.get(k, '')[:50]))


if __name__ == '__main__':
    main()
