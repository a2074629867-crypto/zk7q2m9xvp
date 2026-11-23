# -*- coding: utf-8 -*-
"""diag_vits.py —— 诊断 ft SoVITS 输出：可懂度 + 声学特征"""
import os, sys, wave
import numpy as np

OUT = r'E:/tts-models/acpp/out/v5iso'
ANCHOR = r'G:/_setup/dots_test/_an_real_trim.wav'
BASE = r'E:/tts-models/acpp/out/v5ft/base_1.wav'


def read_wav(p):
    with wave.open(p, 'rb') as w:
        sr = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        raw = w.readframes(n)
    if w.getsampwidth() == 2:
        x = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768.0
    else:
        x = np.frombuffer(raw, dtype='<i4').astype(np.float64) / 2147483648.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    return x, sr


def feats(x, sr):
    # 能量 VAD：取有声帧
    fr = int(0.025 * sr); hop = int(0.010 * sr)
    nf = (len(x) - fr) // hop
    if nf < 10:
        return None
    e = np.array([np.sqrt((x[i*hop:i*hop+fr]**2).mean()) for i in range(nf)])
    thr = max(np.percentile(e, 60) * 0.15, 1e-5)
    voiced = e > thr
    # 用自相关估 F0（只在有声帧）
    f0s = []
    win = x[:nf*hop].reshape(nf, hop) if False else None
    for i in range(0, nf, 2):
        if not voiced[i]:
            continue
        s = x[i*hop:i*hop+int(0.04*sr)]
        if len(s) < 200:
            continue
        s = s - s.mean()
        ac = np.correlate(s, s, 'full')[len(s)-1:]
        lo, hi = int(sr/400), int(sr/60)   # 60-400 Hz
        if hi >= len(ac):
            continue
        seg = ac[lo:hi]
        if len(seg) == 0 or seg.max() <= 0:
            continue
        lag = lo + int(np.argmax(seg))
        if ac[lag] > 0.3 * ac[0]:
            f0s.append(sr / lag)
    f0s = np.array(f0s) if f0s else np.array([np.nan])
    # 谱重心 + 谐波噪声比近似（H1-H2 用 FFT 谱峰差）
    from numpy.fft import rfft, rfftfreq
    sp = np.abs(rfft(x * np.hanning(len(x)))) ** 2
    fq = rfftfreq(len(x), 1/sr)
    m = (fq > 50) & (fq < 8000)
    cen = float((fq[m] * sp[m]).sum() / max(sp[m].sum(), 1e-30))
    rms = float(np.sqrt((x**2).mean()))
    # 语音占比
    spk = float(voiced.mean())
    return dict(f0_med=float(np.nanmedian(f0s)), f0_p10=float(np.nanpercentile(f0s, 10)),
                f0_p90=float(np.nanpercentile(f0s, 90)), f0_n=int(np.sum(~np.isnan(f0s))),
                centroid=cen, rms=rms, voiced=spk)


print('%-28s %8s %8s %8s %9s %8s %7s %7s' %
      ('文件', 'F0中位', 'F0p10', 'F0p90', '谱重心', 'RMS', '语音占比', '时长'))
for tag, p in [('真人 anchor(real_trim)', ANCHOR), ('base_1 (零样本)', BASE),
               ('ft_vits+baseGPT', OUT + '/1_ftvits_basegpt.wav'),
               ('base+base (对照)', OUT + '/4_base_base.wav')]:
    if not os.path.exists(p):
        print('%-28s  缺失 %s' % (tag, p)); continue
    x, sr = read_wav(p)
    f = feats(x, sr)
    if f is None:
        print('%-28s  太短' % tag); continue
    print('%-28s %8.1f %8.1f %8.1f %9.0f %8.4f %6.1f%% %6.2fs' % (
        tag, f['f0_med'], f['f0_p10'], f['f0_p90'], f['centroid'], f['rms'],
        100*f['voiced'], len(x)/sr))

