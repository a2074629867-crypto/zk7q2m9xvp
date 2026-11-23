# -*- coding: utf-8 -*-
"""_timbre_whole.py —— 整条音频的声纹零分布（不切段、不补长）

验证：整条 5~20s 直接提嵌入时，同一 voice 的条间相似度是多少。
如果中位 >= 0.65，说明整条口径可用，句内切段口径应废弃。
"""
import os, sys, json, itertools
import numpy as np

sys.path.insert(0, 'G:/_setup')
import ch123_segcheck as CS

AUD = 'G:/_setup/_audio_ch123/out'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 16
units = [x['unit'] for x in json.load(open('G:/_setup/_narr_check4/_narr_check.json', encoding='utf-8'))]
step = max(1, len(units) // N)
sample = units[::step][:N]

os.makedirs('_segchk_whole', exist_ok=True)
E, D = [], []
for u in sample:
    p = os.path.join(AUD, u + '.wav')
    if not os.path.exists(p):
        continue
    a, sr = CS.read_wav(p)
    d = len(a) / sr
    fp = os.path.join('_segchk_whole', u + '.wav')
    CS.write_wav(fp, a, sr)
    E.append((u, CS.SPK.embed(fp)))
    D.append(d)
    print('  %s %.2fs' % (u, d), flush=True)

sims = []
for (ua, ea), (ub, eb) in itertools.combinations(E, 2):
    sims.append(CS.SPK.cos(ea, eb))
sims = np.array(sims)
print('\n整条条间相似度 n=%d  min %.3f  p10 %.3f  中位 %.3f  p90 %.3f  max %.3f' % (
    len(sims), sims.min(), np.percentile(sims, 10), np.median(sims),
    np.percentile(sims, 90), sims.max()))
print('<0.65 比例 %.0f%%   <0.55 比例 %.0f%%' % (
    100*np.mean(sims < 0.65), 100*np.mean(sims < 0.55)))
