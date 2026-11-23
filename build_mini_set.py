# -*- coding: utf-8 -*-
"""从 461 片里挑最干净的 24 片（voiced 高 + maxsil 低），构造过拟合测试集。
目的：24 片训 60 epoch，若能把文本背下来 -> 管线通，问题在数据质量；
      若仍塌缩 -> 管线有结构性问题。
"""
import json, re
from pathlib import Path

D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')
SQ = json.load(open('G:/GPT-SoVITS/_dataset_v5full/slice_quality.json', encoding='utf-8'))

names = []
for line in (D/'6-name2semantic.tsv').read_text(encoding='utf-8').splitlines():
    p = line.split('\t')
    if len(p) >= 2:
        names.append(Path(p[0]).name)

scored = []
for n in names:
    q = SQ.get(n)
    if not q: continue
    scored.append((q['voiced'] - 1.2*q['maxsil'], n, q['voiced'], q['maxsil']))
scored.sort(reverse=True)
pick = [x[1] for x in scored[:24]]
print('挑选的 24 片（voiced/maxsil）:')
for x in scored[:24]:
    print('  %-46s voiced=%.2f maxsil=%.2f' % (x[1][-44:], x[2], x[3]))

# 写子集
def sub(src, dst, sep='\t'):
    out = []
    for line in (D/src).read_text(encoding='utf-8').splitlines():
        for n in pick:
            if n in line:
                out.append(line)
                break
    Path(dst).write_text('\n'.join(out) + '\n', encoding='utf-8')
    print('%s -> %d 行' % (dst, len(out)))

sub('2-name2text.txt', 'G:/_setup/mini_2-name2text.txt')
sub('6-name2semantic.tsv', 'G:/_setup/mini_6-name2semantic.tsv')
