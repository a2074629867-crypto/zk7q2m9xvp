# -*- coding: utf-8 -*-
"""列出音频的所有间隙时长（能量 VAD -35dB），用于对照真人停顿分布。"""
import sys
import numpy as np, soundfile as sf
SR = 48000
def segs_of(p):
    x, sr = sf.read(p, dtype='float64', always_2d=True); x = x.mean(1)
    hop = int(SR*0.010); n = len(x)//hop
    db = 20*np.log10(np.sqrt((x[:n*hop].reshape(n,hop)**2).mean(1))+1e-12)
    sp = db > (db.max()-35.0)
    m = sp.copy(); i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]: j += 1
            if i > 0 and j < len(m) and (j-i) < 8: m[i:j] = True
            i = j
        else: i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]: j += 1
            if (j-i) < 12: m[i:j] = False
            i = j
        else: i += 1
    out = []; i = 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]: j += 1
            out.append((i*0.01, j*0.01)); i = j
        else: i += 1
    return x, out
for p in sys.argv[1:]:
    x, s = segs_of(p)
    gs = [s[k][0]-s[k-1][1] for k in range(1, len(s))]
    gs = [g for g in gs if g > 0.05]
    print('%-24s %.2fs  间隙 %d 个: %s' % (p.split('/')[-1], len(x)/SR, len(gs),
          ' '.join('%.2f' % g for g in gs)))
