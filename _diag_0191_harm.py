# -*- coding: utf-8 -*-
"""much(1.05~1.11s) 的谐波结构：判 144Hz 是基频还是 72Hz 的二次谐波。"""
import numpy as np, soundfile as sf

p = r"G:\_setup\_audio_ch123\out\c2_0191.wav"
y, sr = sf.read(p, dtype="float32")
if y.ndim > 1:
    y = y.mean(1)
a, b = int(1.05 * sr), int(1.11 * sr)
seg = y[a:b].astype(np.float64)
seg *= np.hanning(len(seg))
S = np.abs(np.fft.rfft(seg, n=1 << 16))
f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
# 只看 50~500Hz 的局部峰
lo = (f > 50) & (f < 500)
fs, ms = f[lo], S[lo]
idx = []
for i in range(1, len(ms) - 1):
    if ms[i] > ms[i - 1] and ms[i] > ms[i + 1]:
        idx.append(i)
idx = sorted(idx, key=lambda i: -ms[i])[:8]
print("1.05~1.11s 段（much）50-500Hz 谱峰：")
for i in idx:
    print("  %7.1f Hz   %.4f  (%+.1f dB rel top)" % (fs[i], ms[i], 20 * np.log10(ms[i] / ms[idx[0]] + 1e-12)))

# 对照：同样方法看 0.94~1.00（been 尾，应稳定）
a, b = int(0.94 * sr), int(1.00 * sr)
seg = y[a:b].astype(np.float64)
seg *= np.hanning(len(seg))
S2 = np.abs(np.fft.rfft(seg, n=1 << 16))
ms2 = S2[lo]
idx2 = []
for i in range(1, len(ms2) - 1):
    if ms2[i] > ms2[i - 1] and ms2[i] > ms2[i + 1]:
        idx2.append(i)
idx2 = sorted(idx2, key=lambda i: -ms2[i])[:6]
print("\n0.94~1.00s 段（been 尾）对照：")
for i in idx2:
    print("  %7.1f Hz   %.4f" % (fs[i], ms2[i]))
