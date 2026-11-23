# -*- coding: utf-8 -*-
"""mt_pause_shape.py —— 量「停顿形状」：同一句里每处停顿是等长还是有长有短。

对三组数据做同样的度量：
  A. 马修真人母带（词级对齐 wonder_final.json）
  B. 我们生成的 59 条（ch123_final，word_times ASR）
  C. 当前生产系统处理后（ch123_final_pause）

输出每组的 gap 分布、同句内变异（句内 sd / 句间 sd）、以及"同标点不同长度"的证据。

用法: python mt_pause_shape.py
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, r'G:/_setup')

WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
PUNCT = set(".,?!;:")


def human_gaps():
    d = json.load(open(WORDS, encoding="utf-8"))
    out = []
    for s in d["slices"]:
        ws = s.get("words", [])
        for k in range(len(ws) - 1):
            t1, w = float(ws[k][1]), ws[k][2]
            t0n = float(ws[k + 1][0])
            g = t0n - t1
            if g < 0.03:
                continue
            tok = w.strip()
            p = tok[-1] if tok and tok[-1] in PUNCT else ""
            out.append(dict(gap=g, punct=p, prev=tok, sid=len(out) // 3))
    return out


def our_gaps(directory):
    from _wtlib import word_times_cached as wt
    rows = []
    for f in sorted(glob.glob(os.path.join(directory, '*.wav'))):
        k = os.path.basename(f)[:-4]
        try:
            rw = wt(f)
        except Exception as e:
            print('  [warn] %s %s' % (k, e))
            continue
        for j in range(len(rw) - 1):
            a, b, w = rw[j]
            g = rw[j + 1][0] - b
            if g < 0.03:
                continue
            tok = w.strip()
            p = tok[-1] if tok and tok[-1] in PUNCT else ""
            rows.append(dict(gap=g, punct=p, prev=tok, key=k))
    return rows


def report(name, rows, key='key'):
    g = np.array([r['gap'] for r in rows])
    print('== %s  n=%d' % (name, len(g)))
    print('   gap  中位 %.2fs  IQR %.2f~%.2f  p10 %.2f  p90 %.2f  跨度 %.2f~%.2f  sd %.2f'
          % (np.median(g), np.percentile(g, 25), np.percentile(g, 75),
             np.percentile(g, 10), np.percentile(g, 90), g.min(), g.max(), g.std()))
    for p, label in (('.', '句号'), (',', '逗号')):
        v = np.array([r['gap'] for r in rows if r['punct'] == p])
        if len(v) >= 3:
            print('   %s n=%3d 中位 %.2fs  IQR %.2f~%.2f  sd %.2f  跨度 %.2f~%.2f'
                  % (label, len(v), np.median(v), np.percentile(v, 25),
                     np.percentile(v, 75), v.std(), v.min(), v.max()))
    # 句内变异 vs 句间变异
    by = defaultdict(list)
    for r in rows:
        by[r[key]].append(r['gap'])
    within = [np.std(v, ddof=1) for v in by.values() if len(v) >= 2]
    if within:
        print('   同句内 sd 中位 %.2fs（n=%d 句）' % (np.median(within), len(within)))
    print()


def main():
    print()
    h = human_gaps()
    report('A 马修真人母带', h, 'sid')
    b = our_gaps(r'G:/_setup/ch123_final')
    report('B 我们生成（未处理）', b)
    c = our_gaps(r'G:/_setup/ch123_final_pause')
    report('C 当前生产系统（处理后）', c)

    # 直方图：看有没有"都挤在同一个值"
    print('== gap 分布直方图（0.2s 桶，只显示 >=0.15s）==')
    for name, rows in (('真人', h), ('生成', b), ('处理后', c)):
        g = np.array([r['gap'] for r in rows])
        bins = np.arange(0.15, 2.55, 0.2)
        cnt, _ = np.histogram(g, bins=bins)
        top = np.argsort(-cnt)[:3]
        print('  %-6s 峰值桶: %s' % (name, '  '.join(
            '%.1f-%.1f:%d' % (bins[i], bins[i] + 0.2, cnt[i]) for i in top)))
        bars = ''.join('#' if v > 0 else '.' for v in cnt)
        print('         [%s]' % bars)


if __name__ == '__main__':
    main()
