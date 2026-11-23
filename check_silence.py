# -*- coding: utf-8 -*-
"""能量法验证：片尾标点 vs 片末实际静音长度（Parakeet 词级时间戳只有 80ms 粒度，不可靠）"""
import json, numpy as np, soundfile as sf

D = 'G:/GPT-SoVITS/_dataset_v5full/'
SR = 32000
L = json.load(open(D + 'wonder_hp.json', encoding='utf-8'))['slices']
x, sr = sf.read('G:/_setup/_denoise_full/wonder_train_df3hp.wav', dtype='float64', always_2d=True)
x = x.mean(1)
peak = np.abs(x).max()
thr = peak * 10 ** (-35 / 20.0)          # -35 dB rel peak
print('峰值 %.4f | 静音阈值 %.6f (-35dB rel peak)' % (peak, thr))

def sil_len(a, b):
    """[a,b] 区间末尾的连续静音长度（从 b 往前扫 10ms 帧）"""
    i0, i1 = int(a * SR), int(b * SR)
    if i1 <= i0:
        return 0.0
    seg = x[i0:i1]
    fl = int(0.010 * SR)
    n = len(seg) // fl
    if n == 0:
        return 0.0
    e = np.array([np.sqrt((seg[k * fl:(k + 1) * fl] ** 2).mean()) for k in range(n)])
    k = n - 1
    while k >= 0 and e[k] < thr:
        k -= 1
    return (n - 1 - k) * 0.010

def cls(w):
    w = w.strip()
    if w.endswith(','):
        return 'comma'
    if w.endswith('.'):
        return 'period'
    if w.endswith('?') or w.endswith('!'):
        return 'qexcl'
    return 'none'

import collections
g = collections.defaultdict(list)
for s in L:
    if not s['words']:
        continue
    we = s['words'][-1][1]           # 末词结束时间
    g[cls(s['words'][-1][2])].append(sil_len(we, s['t1']))

print()
print('=== 片末静音长度（末词结束 -> 切片结束）按片尾标点分组 ===')
print('%-10s %6s %8s %8s %8s %8s %10s' % ('片尾标点', 'n', 'p25', '中位', 'p75', 'p90', '>=0.25s占比'))
for k in ['none', 'comma', 'period', 'qexcl']:
    v = np.array(g[k]) if g[k] else np.array([0.0])
    frac = 100.0 * (v >= 0.25).mean() if len(g[k]) else 0.0
    print('  %-8s %6d %8.3f %8.3f %8.3f %8.3f %9.0f%%' % (
        k, len(g[k]), np.percentile(v, 25), np.median(v),
        np.percentile(v, 75), np.percentile(v, 90), frac))

print()
print('=== 片内标点后是否真有静音（抽 15 例）===')
cnt = 0
for s in L:
    ws = s['words']
    for i in range(len(ws) - 1):
        if ws[i][2].strip().endswith(('.', ',')):
            sl = sil_len(ws[i][1], ws[i + 1][0])
            print('  [%8.2f] %-16s -> %-14s  停顿 %.3fs %s' % (
                ws[i][1], ws[i][2], ws[i + 1][2], sl,
                'OK' if sl >= 0.10 else '!! 无静音'))
            cnt += 1
            break
    if cnt >= 15:
        break
