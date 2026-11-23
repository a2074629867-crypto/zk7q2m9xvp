# -*- coding: utf-8 -*-
"""剔除静音后重算 语音帧/phoneme —— 判断"8倍跨度"是不是纯由静音含量造成的"""
import os, re, sys, json
from pathlib import Path
sys.path.insert(0, 'G:/_setup/gsv5probe'); sys.path.insert(0, 'G:/_setup/gsv5probe/GPT_SoVITS')
os.chdir('G:/_setup/gsv5probe'); os.environ['version'] = 'v5turbo'
from text import cleaned_text_to_sequence
import numpy as np

D = Path('G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp')
SQ = json.load(open('G:/GPT-SoVITS/_dataset_v5full/slice_quality.json', encoding='utf-8'))
# 看结构
k0 = list(SQ.keys())[:2] if isinstance(SQ, dict) else None
if isinstance(SQ, dict):
    print('slice_quality keys 示例:', k0, '| 值示例:', SQ[k0[0]] if k0 else None)
elif isinstance(SQ, list):
    print('slice_quality list 示例:', SQ[0])

HZ = 25.0
ph = {}
for line in (D/'2-name2text.txt').read_text(encoding='utf-8').splitlines():
    p = line.split('\t')
    if len(p) >= 4: ph[Path(p[0]).name] = p[1]

def getq(name):
    if isinstance(SQ, dict):
        v = SQ.get(name) or SQ.get(name.replace('.wav',''))
        return v
    for it in SQ:
        if it.get('file') == name: return it
    return None

rows = []
for line in (D/'6-name2semantic.tsv').read_text(encoding='utf-8').splitlines():
    p = line.split('\t')
    if len(p) < 2: continue
    name = Path(p[0]).name
    if name not in ph: continue
    q = getq(name) or {}
    voiced = q.get('voiced', None)
    maxsil = q.get('maxsil', None)
    sem = len(p[1].split())
    ids = cleaned_text_to_sequence(ph[name].split(' '), 'v5turbo')
    if not ids: continue
    rows.append((sem, len(ids), voiced, maxsil))

v = [r for r in rows if r[2] is not None]
print('\n有 voiced 数据的样本: %d/%d' % (len(v), len(rows)))
if v:
    a = np.array([[r[0], r[1], r[2]] for r in v])
    voiced_frames = a[:,0]*a[:,2]
    ratio_all = a[:,0]/a[:,1]
    ratio_v   = voiced_frames/a[:,1]
    print('静音占比 (1-voiced): 中位 %.1f%%   最差 %.1f%%' % ((1-a[:,2].mean())*100, (1-a[:,2].min())*100))
    print('\n帧/phoneme       : 中位 %.3f  min %.3f  max %.3f  跨度 %.1fx' % (np.median(ratio_all), ratio_all.min(), ratio_all.max(), ratio_all.max()/ratio_all.min()))
    print('语音帧/phoneme   : 中位 %.3f  min %.3f  max %.3f  跨度 %.1fx' % (np.median(ratio_v), ratio_v.min(), ratio_v.max(), ratio_v.max()/ratio_v.min()))
    print('  → 剔除静音后方差降了 %.1f 倍' % ((ratio_all.max()/ratio_all.min())/(ratio_v.max()/ratio_v.min())))
    print('语音帧/phoneme 标准差: %.4f  (原 %.4f)' % (ratio_v.std(), ratio_all.std()))

ms = [r for r in rows if r[3] is not None]
if ms:
    m = np.array([r[3] for r in ms])
    print('\n最长连续静音 maxsil: 中位 %.2fs  p75 %.2fs  max %.2fs' % (np.median(m), np.percentile(m,75), m.max()))
    print('maxsil>1.0s 的样本: %d/%d (%.0f%%)' % ((m>1.0).sum(), len(m), (m>1.0).mean()*100))
    keep = np.array([r[3] for r in ms]) <= 1.0
    idx = [i for i,r in enumerate(rows) if r[3] is not None and r[3] <= 1.0]
    sub = np.array([[rows[i][0], rows[i][1]] for i in idx])
    rr = sub[:,0]/sub[:,1]
    print('  过滤后(maxsil<=1s, n=%d) 帧/phoneme: 中位 %.3f 跨度 %.1fx' % (len(sub), np.median(rr), rr.max()/rr.min()))
