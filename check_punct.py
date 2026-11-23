# -*- coding: utf-8 -*-
"""检查 list 的标点是否与音频实际停顿一致（GSV 标点是训练符号）"""
import json, numpy as np, collections

D = 'G:/GPT-SoVITS/_dataset_v5full/'
L = json.load(open(D + 'wonder_hp.json', encoding='utf-8'))['slices']


def cls(w):
    w = w.strip()
    if w.endswith(','):
        return 'comma'
    if w.endswith('.'):
        return 'period'
    if w.endswith('?') or w.endswith('!'):
        return 'qexcl'
    return 'none'


print('=== A) 片内停顿（标点词 -> 下一词）===')
g = collections.defaultdict(list)
for s in L:
    ws = s['words']
    for i in range(len(ws) - 1):
        g[cls(ws[i][2])].append(ws[i + 1][0] - ws[i][1])
print('%-10s %6s %8s %8s %8s %8s' % ('标点', 'n', 'p25', '中位', 'p75', 'p90'))
for k in ['none', 'comma', 'period', 'qexcl']:
    v = np.array(g[k]) if g[k] else np.array([0.0])
    print('  %-8s %6d %8.3f %8.3f %8.3f %8.3f' % (k, len(g[k]),
          np.percentile(v, 25), np.median(v), np.percentile(v, 75), np.percentile(v, 90)))

print()
print('=== B) 跨片停顿（本片末词 -> 下片首词，= 完整停顿）===')
c = collections.defaultdict(list)
for i in range(len(L) - 1):
    a, b = L[i], L[i + 1]
    if not a['words'] or not b['words']:
        continue
    c[cls(a['words'][-1][2])].append(b['words'][0][0] - a['words'][-1][1])
print('%-10s %6s %8s %8s %8s %8s' % ('片尾标点', 'n', 'p25', '中位', 'p75', 'p90'))
for k in ['none', 'comma', 'period', 'qexcl']:
    v = np.array(c[k]) if c[k] else np.array([0.0])
    print('  %-8s %6d %8.3f %8.3f %8.3f %8.3f' % (k, len(c[k]),
          np.percentile(v, 25), np.median(v), np.percentile(v, 75), np.percentile(v, 90)))

print()
print('=== C) 标点字符集检查（GSV 支持: . , ! ? … -）===')
chars = collections.Counter()
for s in L:
    for ch in s['text']:
        if not (ch.isalnum() or ch.isspace() or ch == "'"):
            chars[ch] += 1
print('  非字母数字字符:', dict(chars))
bad = {k: v for k, v in chars.items() if k not in '.,!?…-\''}
print('  GSV 不支持的:', bad if bad else '无 ✓')

print()
print('=== D) 与音频停顿的一致性判定 ===')
def med(k, d=g):
    return float(np.median(d[k])) if d[k] else 0.0
mn, mc, mp = med('none'), med('comma'), med('period')
print('  片内: 无标点 %.3fs < 逗号 %.3fs < 句号 %.3fs  %s'
      % (mn, mc, mp, '✓ 单调递增' if mn <= mc <= mp else '✗ 顺序异常'))
mn2, mc2, mp2 = med('none', c), med('comma', c), med('period', c)
print('  跨片: 无标点 %.3fs < 逗号 %.3fs < 句号 %.3fs  %s'
      % (mn2, mc2, mp2, '✓ 单调递增' if mn2 <= mc2 <= mp2 else '✗ 顺序异常'))
