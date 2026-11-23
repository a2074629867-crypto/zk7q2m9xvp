# -*- coding: utf-8 -*-
"""诊断词间停顿：donor（真实原声）vs receiver（生成）在逗号/句号处各停多久。

用法:
  python -u diag_pauses.py --donor real.wav --recv gen.wav --recv2 transplant.wav
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, r'G:/_setup')
from transplant_prosody2 import word_times  # noqa: E402


def gaps(ws):
    """返回 [(idx, word, gap_after_sec)]，gap = 下一词起点 - 本词终点。"""
    out = []
    for i in range(len(ws) - 1):
        s, e, t = ws[i]
        ns = ws[i + 1][0]
        out.append((i, t, float(ns - e)))
    return out


def show(tag, wav):
    if not os.path.exists(wav):
        print('  %-14s (缺文件)' % tag)
        return None
    ws = word_times(wav)
    if not ws:
        print('  %-14s (无词)' % tag)
        return None
    g = gaps(ws)
    dur = ws[-1][1] - ws[0][0]
    print('  %-14s %d词  %.2fs  词间gap: 中位%.3f 最大%.3f' %
          (tag, len(ws), dur, np.median([x[2] for x in g]) if g else 0,
           max([x[2] for x in g]) if g else 0))
    for i, t, gp in g:
        mark = ''
        w = ws[i][2]
        if w.endswith(',') or w.endswith(';'):
            mark = '  ← 逗号'
        elif w.endswith('.') or w.endswith('?') or w.endswith('!'):
            mark = '  ← 句末'
        if mark or gp > 0.20:
            print('       %-14s gap=%.3fs%s' % (w, gp, mark))
    return ws, g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--donor', required=True)
    ap.add_argument('--recv', required=True)
    ap.add_argument('--recv2', default='')
    a = ap.parse_args()

    print('=== %s ===' % os.path.basename(a.recv))
    r1 = show('真实原声', a.donor)
    r2 = show('生成', a.recv)
    if a.recv2:
        show('移植后', a.recv2)

    if r1 and r2:
        ws1, g1 = r1
        ws2, g2 = r2
        if len(ws1) == len(ws2):
            print()
            print('  逐词 gap 对比（真实 vs 生成）:')
            for (i1, t1, gp1), (i2, t2, gp2) in zip(g1, g2):
                w = ws1[i1][2]
                d = gp2 - gp1
                flag = ''
                if (w.endswith(',') or w.endswith('.') or w.endswith(';')) and d < -0.05:
                    flag = '  ← 少停了 %.0fms' % (-d * 1000)
                elif gp1 > 0.12 or gp2 > 0.12:
                    flag = '  (%+.0fms)' % (d * 1000)
                if flag:
                    print('       %-14s 真实%.3f 生成%.3f%s' % (w, gp1, gp2, flag))


if __name__ == '__main__':
    main()
