# -*- coding: utf-8 -*-
"""同法对比 旧切片(sliced_df3hp, max_sil_kept=3000) vs 新切片(sliced_v6, max_sil_kept=700)
指标：每片时长 / 语音占比(能量VAD -35dB rel peak) / 最长连续静音
"""
import sys, glob, os
import numpy as np, soundfile as sf

def vad(path):
    a, sr = sf.read(path, dtype='float32')
    if a.ndim > 1: a = a.mean(1)
    hop = int(sr*0.010)  # 10ms
    n = len(a)//hop
    fr = a[:n*hop].reshape(n, hop)
    rms = np.sqrt((fr**2).mean(1) + 1e-12)
    db = 20*np.log10(rms + 1e-12)
    thr = db.max() - 35.0
    speech = db > thr
    if speech.sum() == 0: return len(a)/sr, 0.0, len(a)/sr
    # 最长连续静音
    best = cur = 0
    for s in speech:
        if s: cur = 0
        else:
            cur += 1; best = max(best, cur)
    return len(a)/sr, speech.mean(), best*0.01

for tag, d in [('旧 max_sil_kept=3000', 'G:/GPT-SoVITS/_dataset_v5full/sliced_df3hp'),
               ('新 max_sil_kept=700',  'G:/GPT-SoVITS/_dataset_v5full/sliced_v6')]:
    fs = sorted(glob.glob(d + '/*.wav'))
    rows = [vad(f) for f in fs]
    dur = np.array([r[0] for r in rows]); voi = np.array([r[1] for r in rows]); ms = np.array([r[2] for r in rows])
    print('=== %s ===' % tag)
    print('  片数 %d   总时长 %.1f min' % (len(fs), dur.sum()/60))
    print('  时长  : 中位 %.2fs  max %.2fs' % (np.median(dur), dur.max()))
    print('  语音占比: 中位 %.3f  p25 %.3f  p75 %.3f' % (np.median(voi), np.percentile(voi,25), np.percentile(voi,75)))
    print('  最长静音: 中位 %.2fs  p75 %.2fs  p90 %.2fs' % (np.median(ms), np.percentile(ms,75), np.percentile(ms,90)))
    print('  maxsil>1.0s 的片: %d (%.0f%%)' % ((ms>1.0).sum(), (ms>1.0).mean()*100))
    print('  干净片(voi>=0.6 且 ms<=0.8): %d (%.0f%%)' % (((voi>=0.6)&(ms<=0.8)).sum(), ((voi>=0.6)&(ms<=0.8)).mean()*100))
    print()
