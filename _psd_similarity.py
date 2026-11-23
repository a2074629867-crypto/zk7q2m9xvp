# -*- coding: utf-8 -*-
"""逐条 PSD 谱形相似度：决定插槽纹理该用「本文件谱」还是「统一面板」。"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, r'G:/_setup')
from mt_final_pause import MIN_QUIET_FRAMES, measure, noise_psd

rows = []
for f in sorted(glob.glob(r'G:/_setup/ch123_final/*.wav')):
    k = os.path.basename(f)[:-4]
    x, sr = sf.read(f, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    x = np.ascontiguousarray(x, dtype=np.float32)
    st = measure(x, sr)
    if st['nq'] < MIN_QUIET_FRAMES:
        print('%-5s 跳过（quiet n=%d）' % (k, st['nq']))
        continue
    psd = noise_psd(x, sr, st['db'], st['n'], st['h'], st['mask'])
    if psd is None:
        print('%-5s PSD 不可用' % k)
        continue
    fq, p = psd
    v = np.log(np.maximum(p, 1e-30))
    v = v - v.mean()
    rows.append((k, v, st['level']))

ks = [r[0] for r in rows]
M = np.asarray([r[1] for r in rows])
N = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)
S = N @ N.T
np.fill_diagonal(S, np.nan)
print('\n谱形余弦（去均值 log PSD）n=%d' % len(rows))
print('  中位 %.3f  p05 %.3f  p95 %.3f  min %.3f' % (
    np.nanmedian(S), np.nanpercentile(S, 5), np.nanpercentile(S, 95), np.nanmin(S)))
med = np.nanmedian(M, axis=0)
mn = (med - med.mean()) / (np.linalg.norm(med - med.mean()) + 1e-12)
cos_panel = N @ mn
print('  对「全库中位面板」的余弦：中位 %.3f  min %.3f  max %.3f'
      % (np.median(cos_panel), cos_panel.min(), cos_panel.max()))
worst = np.argsort(cos_panel)[:5]
print('  偏离最大的 5 条: ' + '  '.join('%s(%.2f)' % (ks[i], cos_panel[i]) for i in worst))

# 谱倾斜度（低频/高频能量比）视角
slope = []
for k, v, lv in rows:
    lo = v[:len(v) // 4].mean()
    hi = v[len(v) // 2:].mean()
    slope.append((k, lo - hi, lv))
slope.sort(key=lambda t: t[1])
print('\n谱倾斜（低4分位−高半段, dB）: 最平 %s %.1f / 中位 %.1f / 最陡 %s %.1f' %
      (slope[0][0], slope[0][1], slope[len(slope) // 2][1], slope[-1][0], slope[-1][1]))
