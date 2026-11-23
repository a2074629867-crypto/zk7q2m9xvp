# -*- coding: utf-8 -*-
"""mt_matt_annot_agree.py —— 马修旁白三方标注交叉验证 + 时长验证。

两件事：
1. 一致性：三方圆桌 + Fleiss' Kappa
2. ★ 关键验证：标注的 kind 能不能分开实测停顿时长
   —— 这是「语义分类对时长有预测力」的唯一证据。
      分不开就说明这套语义标签没用，得换。
"""
import json
import sys
from collections import Counter, defaultdict

FILES = {
    'main': r'G:/_setup/_annot_matt_main.json',
    'hy4': r'G:/_setup/_annot_matt_hy4.json',
    'ds': r'G:/_setup/_annot_matt_ds.json',
}
SAMPLES = r'G:/_setup/_matt_annot_samples.json'
ORDER = ['drop', 'tight', 'clause', 'beat', 'paragraph']


def load(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print('  [FAIL] %s: %s' % (path, e))
        return None
    # 容错：多包一层 / 值不是 dict
    if isinstance(d, dict) and len(d) == 1 and 'P001' not in d:
        inner = list(d.values())[0]
        if isinstance(inner, dict) and 'P001' in inner:
            d = inner
    out = {}
    for k, v in d.items():
        if not isinstance(k, str) or not k.startswith('P'):
            continue
        if isinstance(v, str):
            out[k] = {'kind': v, 'why': ''}
        elif isinstance(v, dict):
            out[k] = {'kind': v.get('kind') or v.get('label') or '?',
                      'why': v.get('why', '')}
    return out


def fleiss(rows):
    items = [r for r in rows if len(r) >= 2]
    if not items:
        return None, None, None
    cats = sorted(set(l for r in items for l in r))
    N, n = len(items), len(items[0])
    P = []
    for r in items:
        c = Counter(r)
        P.append((sum(v * v for v in c.values()) - n) / (n * (n - 1)))
    P_bar = sum(P) / N
    tot = Counter()
    for r in items:
        for l in r:
            tot[l] += 1
    P_e = sum((v / (N * n)) ** 2 for v in tot.values())
    if P_e >= 1:
        return 1.0, P_bar, P_e
    return (P_bar - P_e) / (1 - P_e), P_bar, P_e


def main():
    ann = {}
    for nm, p in FILES.items():
        d = load(p)
        if d:
            ann[nm] = d
    if len(ann) < 2:
        print('可用标注者 <2')
        return
    names = list(ann)
    print('可用标注者: %s' % ', '.join(names))

    samples = {s['key']: s for s in json.load(open(SAMPLES, encoding='utf-8'))}
    keys = sorted(samples)
    for nm in names:
        miss = [k for k in keys if k not in ann[nm]]
        extra = [k for k in ann[nm] if k not in samples]
        print('  %-5s 覆盖 %d/%d%s%s' % (nm, len(keys) - len(miss), len(keys),
                                        '  缺:%s' % miss[:5] if miss else '',
                                        '  多:%s' % extra[:3] if extra else ''))

    print('\n=== 逐条一致性 ===')
    per = []
    for k in keys:
        labs = [ann[nm][k]['kind'] for nm in names if k in ann[nm]]
        if len(labs) >= 2:
            per.append((k, labs))
    full = sum(1 for _, l in per if len(set(l)) == 1)
    print('  可对齐 %d 条' % len(per))
    print('  全一致 %d (%.0f%%)' % (full, 100 * full / max(1, len(per))))
    kap, pb, pe = fleiss([l for _, l in per])
    if kap is not None:
        print("  Fleiss' Kappa = %.3f  (P_bar %.3f / P_e %.3f)" % (kap, pb, pe))
        if kap >= 0.7:
            print('  → 一致性良好，可直接扩量')
        elif kap >= 0.6:
            print('  → 可接受，但需看分歧模式')
        elif kap >= 0.4:
            print('  → 中等，判据需再收紧')
        else:
            print('  → 不足，判据或任务设计有问题')

    print('\n=== 分歧清单 ===')
    for k, l in per:
        if len(set(l)) == 1:
            continue
        tag = '全分歧' if len(set(l)) == 3 else '2:1'
        print('  %-5s %-6s %s' % (k, tag, dict(zip(names, l))))
        print('         %s' % samples[k]['text'][:88])

    print('\n=== 各标注者的 kind 分布 ===')
    for nm in names:
        c = Counter(ann[nm][k]['kind'] for k in keys if k in ann[nm])
        print('  %-5s %s' % (nm, {x: c.get(x, 0) for x in ORDER if c.get(x)}))

    # ---- 关键：kind 能否分开实测时长
    print('\n=== ★ 语义标签 vs 实测停顿时长 ===')
    print('  （用「全一致」的条目，避免噪声；同时给出全量）')
    for label, subset in (('全一致', [k for k, l in per if len(set(l)) == 1]),):
        g = defaultdict(list)
        for k in subset:
            g[ann[names[0]][k]['kind']].append(samples[k]['_gap'])
        print('  %s n=%d:' % (label, len(subset)))
        print('    %-10s %4s %8s %8s %8s' % ('kind', 'n', '中位', 'p25', 'p75'))
        for kk in ORDER:
            v = g.get(kk)
            if not v:
                continue
            v = sorted(v)
            import statistics
            med = statistics.median(v)
            p25 = v[max(0, int(0.25 * (len(v) - 1)))]
            p75 = v[min(len(v) - 1, int(0.75 * (len(v) - 1)))]
            print('    %-10s %4d %8.2f %8.2f %8.2f' % (kk, len(v), med, p25, p75))

    # 全量（各标注者独立看）
    print('\n  各标注者独立分组（全 40 条）:')
    for nm in names:
        g = defaultdict(list)
        for k in keys:
            if k in ann[nm]:
                g[ann[nm][k]['kind']].append(samples[k]['_gap'])
        parts = []
        for kk in ORDER:
            if g.get(kk):
                v = sorted(g[kk])
                import statistics
                parts.append('%s n=%d 中位%.2f' % (kk, len(v), statistics.median(v)))
        print('    %-5s %s' % (nm, ' | '.join(parts)))

    # 单调性检验：drop < tight < clause < beat < paragraph ？
    print('\n=== 单调性检验（中位时长应递增）===')
    for nm in names:
        g = defaultdict(list)
        for k in keys:
            if k in ann[nm]:
                g[ann[nm][k]['kind']].append(samples[k]['_gap'])
        meds = [(kk, sorted(g[kk])[len(g[kk]) // 2]) for kk in ORDER if g.get(kk)]
        seq = ' < '.join('%s(%.2f)' % x for x in meds)
        ok = all(meds[i][1] <= meds[i + 1][1] for i in range(len(meds) - 1))
        print('  %-5s %s  %s' % (nm, seq, '✓ 单调' if ok else '✗ 非单调'))


if __name__ == '__main__':
    main()
