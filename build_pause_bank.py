# -*- coding: utf-8 -*-
"""统计"标点 → 停顿"原型：从完整原声跑 whisper，按前一词的结尾标点分类统计词间 gap。

产物 pause_bank.json:
  { ",": {n, median, mean, p25, p75, p90}, ".": {...}, ... }
"""
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, r'G:/_setup')
from transplant_prosody2 import word_times  # noqa: E402

SRC = r'G:/GPT-SoVITS/_dataset/wonder_train.wav'
OUT = r'G:/_setup/pause_bank.json'


def tail_punct(w):
    t = w.strip().strip('"\'').strip()
    for ch in reversed(t):
        if ch in ',;:.?!\u2014\u2013':
            return ch
        if ch.isalnum():
            return ''
    return ''


def main():
    ws = word_times(SRC)
    print('词数 %d  时长 %.1fs' % (len(ws), ws[-1][1] - ws[0][0]), flush=True)

    buckets = defaultdict(list)
    allgaps = []
    for i in range(len(ws) - 1):
        gap = float(ws[i + 1][0] - ws[i][1])
        if gap < 0:
            gap = 0.0
        allgaps.append(gap)
        p = tail_punct(ws[i][2])
        if p:
            buckets[p].append(gap)

    print()
    print('%-6s %5s %8s %8s %8s %8s %8s' % ('标点', 'n', 'median', 'mean', 'p25', 'p75', 'p90'))
    print('-' * 62)
    bank = {}
    for p, g in sorted(buckets.items(), key=lambda x: -len(x[1])):
        g = np.array(g, dtype=float)
        bank[p] = dict(n=int(len(g)), median=float(np.median(g)), mean=float(g.mean()),
                       p25=float(np.percentile(g, 25)), p75=float(np.percentile(g, 75)),
                       p90=float(np.percentile(g, 90)))
        print('%-6s %5d %8.3f %8.3f %8.3f %8.3f %8.3f' %
              (p, len(g), bank[p]['median'], bank[p]['mean'],
               bank[p]['p25'], bank[p]['p75'], bank[p]['p90']))

    ag = np.array(allgaps)
    print()
    print('全部词间 gap: n=%d  median=%.3f  p75=%.3f  p90=%.3f  max=%.3f' %
          (len(ag), np.median(ag), np.percentile(ag, 75), np.percentile(ag, 90), ag.max()))
    print('无标点处 gap 中位 = %.3f' % float(np.median([g for g in allgaps if g < 0.15])))

    json.dump(bank, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n已写入', OUT, flush=True)


if __name__ == '__main__':
    main()
