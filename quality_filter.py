# -*- coding: utf-8 -*-
import json, re
from pathlib import Path
import numpy as np

D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')
SQ = json.load(open('G:/GPT-SoVITS/_dataset_v5full/slice_quality.json', encoding='utf-8'))

names = [Path(l.split('\t')[0]).name for l in (D/'6-name2semantic.tsv').read_text(encoding='utf-8').splitlines() if '\t' in l]
sem = {Path(l.split('\t')[0]).name: len(l.split('\t')[1].split()) for l in (D/'6-name2semantic.tsv').read_text(encoding='utf-8').splitlines() if '\t' in l}

rows = []
for n in names:
    q = SQ.get(n)
    if not q: continue
    rows.append((n, q['voiced'], q['maxsil'], sem.get(n, 0)))

print('总片数 %d' % len(rows))
print('voiced 分布: ', ' '.join('p%d=%.2f' % (p, np.percentile([r[1] for r in rows], p)) for p in (10,25,50,75,90)))
print('maxsil分布: ', ' '.join('p%d=%.2f' % (p, np.percentile([r[2] for r in rows], p)) for p in (10,25,50,75,90)))
print()
for vmin, smax in [(0.60, 0.8), (0.65, 0.6), (0.70, 0.5), (0.75, 0.4), (0.80, 0.35)]:
    keep = [r for r in rows if r[1] >= vmin and r[2] <= smax]
    tot = sum(r[3] for r in keep)/25.0
    print('voiced>=%.2f 且 maxsil<=%.2f : %3d 片  (%.1f 分钟)' % (vmin, smax, len(keep), tot/60))
print()
# 只看 maxsil
for smax in [0.3, 0.5, 0.8, 1.0, 1.5]:
    keep = [r for r in rows if r[2] <= smax]
    print('maxsil<=%.1fs : %3d 片' % (smax, len(keep)))
# 只看 voiced
for vmin in [0.5, 0.6, 0.7, 0.8, 0.9]:
    keep = [r for r in rows if r[1] >= vmin]
    print('voiced>=%.2f : %3d 片' % (vmin, len(keep)))
