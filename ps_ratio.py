# -*- coding: utf-8 -*-
"""算训练数据的 phoneme/sec 与 语义帧/phoneme —— 与 GSV 过滤器阈值(3~25)对照"""
import os, re, sys, statistics
from pathlib import Path
sys.path.insert(0, 'G:/_setup/gsv5probe')
sys.path.insert(0, 'G:/_setup/gsv5probe/GPT_SoVITS')
os.chdir('G:/_setup/gsv5probe')
os.environ['version'] = 'v5turbo'
from text import cleaned_text_to_sequence

D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')
HZ = 25.0

# phoneme strings
ph = {}
for line in (D/'2-name2text.txt').read_text(encoding='utf-8').splitlines():
    p = line.split('\t')
    if len(p) < 4: continue
    ph[Path(p[0]).name] = p[1]

rows = []
for line in (D/'6-name2semantic.tsv').read_text(encoding='utf-8').splitlines():
    p = line.split('\t')
    if len(p) < 2: continue
    name = Path(p[0]).name
    if name not in ph: continue
    m = re.search(r'_(\d+)_(\d+)\.wav$', name)
    dur = (int(m.group(2)) - int(m.group(1)))/32000.0
    sem = len(p[1].split())
    ids = cleaned_text_to_sequence(ph[name].split(' '), 'v5turbo')
    sec = sem / HZ
    rows.append((dur, sem, len(ids), len(ids)/sec, sec/len(ids)))

import numpy as np
a = np.array([[r[0], r[1], r[2], r[3], r[4]] for r in rows])
print('样本数 %d' % len(a))
print('时长 s      : min %.2f  中位 %.2f  max %.2f' % (a[:,0].min(), np.median(a[:,0]), a[:,0].max()))
print('语义帧数    : min %.0f  中位 %.0f  max %.0f' % (a[:,1].min(), np.median(a[:,1]), a[:,1].max()))
print('音素数      : min %.0f  中位 %.0f  max %.0f' % (a[:,2].min(), np.median(a[:,2]), a[:,2].max()))
print()
print('★ phoneme/sec : min %.2f  中位 %.2f  max %.2f   (GSV 过滤器窗口 3~25)' % (a[:,3].min(), np.median(a[:,3]), a[:,3].max()))
print('   正常英语朗读 ≈ 12~16 → 我们中位 %.2f 只有其 %.0f%%' % (np.median(a[:,3]), np.median(a[:,3])/14*100))
print()
print('★ 帧/phoneme  : min %.2f  中位 %.2f  max %.2f  (标准差 %.2f)' % (a[:,4].min(), np.median(a[:,4]), a[:,4].max(), a[:,4].std()))
print('  → 每个音素要吐多少帧，跨度 %.1fx' % (a[:,4].max()/max(a[:,4].min(),1e-6)))
print()
q = np.percentile(a[:,3], [5,25,50,75,95])
print('phoneme/sec 分位: p5=%.2f p25=%.2f p50=%.2f p75=%.2f p95=%.2f' % tuple(q))
print('低于过滤器下限 3 的: %d 个' % int((a[:,3] < 3).sum()))
print('低于 8 的         : %d 个 (%.0f%%)' % int((a[:,3] < 8).sum(), (a[:,3]<8).mean()*100))
