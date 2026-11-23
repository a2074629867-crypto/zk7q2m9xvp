# -*- coding: utf-8 -*-
"""
denoise_hp.py —— 降噪第 3 步：削 20-60Hz 次低频隆隆声（安全版，替代 notch）

为什么不用 notch：
  实测 76-78Hz 是 McConaughey 的嗓音基频（峰位置随语调漂移 70-82Hz、
  语音段比停顿段高 66dB、原始音频停顿段 76Hz 处无嗡声）⇒ notch 会挖空音色。
  真正该削的是 20-60Hz 的次低频隆隆声（-86~-70dB，纯噪声，人声基频以下）。

实现：4 阶 Butterworth 高通 + filtfilt（零相位，无瞬态偏移）
"""
import numpy as np, soundfile as sf, time, sys
from scipy.signal import butter, filtfilt, welch

SR = 32000
SRC = 'G:/_setup/_denoise_full/wonder_train_df3.wav'
OUT = 'G:/_setup/_denoise_full/wonder_train_df3hp.wav'
CUT = 55.0

x, sr = sf.read(SRC, dtype='float64', always_2d=True)
x = x.mean(1)
print('源 %d 样本 %.1fs sr=%d' % (len(x), len(x) / sr, sr), flush=True)

b, a = butter(4, CUT / (sr / 2), btype='highpass')
print('4 阶 Butterworth 高通，截止 %.0f Hz（filtfilt 零相位）' % CUT, flush=True)

t = time.time()
y = filtfilt(b, a, x)
print('滤波 %.1fs' % (time.time() - t), flush=True)

pk = float(np.abs(y).max())
print('峰值 %.4f (%.2f dBFS) | 平均绝对差 %.6f | 相关 %.6f'
      % (pk, 20 * np.log10(pk), np.abs(y - x).mean(), np.corrcoef(x, y)[0, 1]), flush=True)

sf.write(OUT, y.astype(np.float32), sr, subtype='PCM_16')
print('写出', OUT, flush=True)

print()
print('=== 频谱对比（各频带平均 dB）===')
print('%-14s %10s %10s %8s' % ('频带', 'DF3', 'HP', '差'))
BANDS = [(20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 90),
         (90, 120), (120, 200), (200, 500), (500, 2000), (2000, 6000), (6000, 11000)]
res = {}
for tag, s in [('DF3', x), ('HP', y)]:
    f, P = welch(s, fs=sr, nperseg=65536, noverlap=32768)
    res[tag] = (f, 10 * np.log10(P + 1e-30))
f, D1 = res['DF3']
_, D2 = res['HP']
for lo, hi in BANDS:
    m = (f >= lo) & (f < hi)
    print('  %5d-%-6d %10.1f %10.1f %+8.1f' % (lo, hi, D1[m].mean(), D2[m].mean(), D2[m].mean() - D1[m].mean()))

print()
print('=== 关键点：人声基频区是否被动到 ===')
for lo, hi, nm in [(70, 85, '基频核心'), (85, 120, '基频谐波'), (120, 300, '低次谐波')]:
    m = (f >= lo) & (f < hi)
    d = D2[m].mean() - D1[m].mean()
    print('  %-10s %3d-%-4d Hz  变化 %+.2f dB  %s'
          % (nm, lo, hi, d, 'OK 未动' if abs(d) < 0.3 else '注意'))
