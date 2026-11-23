# -*- coding: utf-8 -*-
"""电音频段诊断：逐 1/3 倍频程能量对比 + 谐波梳状度。
用法: python diag_band.py <参考原声> <被测1> [<被测2> ...]
输出:
  ① 各频段相对能量(dB, 以 200-400Hz 为 0dB 参考) —— 看高频是否异常堆积
  ② 谐波梳状度 comb = 在 f0 整数倍处能量 / 在 f0 半整数倍处能量
     → 越高说明声码器"过度周期性"，听感即电音/金属感
  ③ 高频平坦度(6-12kHz) —— 声码器高频 artifact 常表现为噪声状
"""
import sys, os
import numpy as np
import soundfile as sf
import librosa

BANDS = [(60, 120), (120, 250), (250, 500), (500, 1000), (1000, 2000),
         (2000, 3000), (3000, 4000), (4000, 6000), (6000, 8000),
         (8000, 11000), (11000, 16000)]


def band_energy(x, sr, lo, hi):
    n = int(2 ** np.ceil(np.log2(max(len(x), 2048))))
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=n))
    f = np.fft.rfftfreq(n, 1.0 / sr)
    m = (f >= lo) & (f < hi)
    return float((X[m] ** 2).sum())


def comb_ratio(x, sr, fmin=60, fmax=400):
    """谐波梳状度：语音最强帧里，f0 整数倍处 vs 半整数倍处的能量比。"""
    fl = int(0.050 * sr)
    hop = int(0.025 * sr)
    vals = []
    for i in range(max(1, (len(x) - fl) // hop)):
        fr = x[i * hop:i * hop + fl]
        if np.sqrt((fr ** 2).mean()) < 1e-4:
            continue
        fr = fr - fr.mean()
        n = int(2 ** np.ceil(np.log2(fl)))
        X = np.abs(np.fft.rfft(fr * np.hanning(fl), n=n))
        f = np.fft.rfftfreq(n, 1.0 / sr)
        # 自相关找 f0
        ac = np.correlate(fr, fr, 'full')[fl - 1:]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(ac) or hi <= lo:
            continue
        f0 = sr / (lo + int(np.argmax(ac[lo:hi])))
        if not (fmin <= f0 <= fmax):
            continue
        harm, half = [], []
        for h in range(1, 25):
            fh = f0 * h
            if fh > 0.45 * sr:
                break
            harm.append(_peak(X, f, fh))
            fh2 = f0 * (h - 0.5)
            if fh2 > 0.45 * sr:
                break
            half.append(_peak(X, f, fh2))
        if harm and half:
            vals.append(np.mean(harm) / (np.mean(half) + 1e-12))
    return float(np.median(vals)) if vals else 0.0


def _peak(X, f, fc, w=60.0):
    m = (f >= fc - w) & (f <= fc + w)
    return float(X[m].max()) if m.any() else 0.0


def hf_flat(x, sr, lo=6000, hi=12000):
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256)) + 1e-10
    f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    m = (f >= lo) & (f <= hi)
    if not m.any():
        return 0.0
    Sb = S[m]
    return float(np.median(np.exp(np.mean(np.log(Sb), axis=0)) / (np.mean(Sb, axis=0) + 1e-12)))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    ref = sys.argv[1]
    items = sys.argv[2:]
    xr, sr = sf.read(ref)
    if xr.ndim > 1:
        xr = xr.mean(1)
    xr = xr / (np.max(np.abs(xr)) or 1.0)
    ref_e = {b: band_energy(xr, sr, *b) for b in BANDS}
    base = ref_e[(250, 500)] + 1e-12

    print('%-30s %s' % ('文件', ' '.join('%6s' % ('%d-%dk' % (b[0] // 1000 or 0, b[1] // 1000)) for b in BANDS)))
    print('-' * 150)
    hdr = '%-30s' % os.path.basename(ref)[:30]
    print(hdr + ' ' + ' '.join('%6.1f' % (10 * np.log10(ref_e[b] / base)) for b in BANDS) +
          '   comb=%.2f  hfFlat=%.3f' % (comb_ratio(xr, sr), hf_flat(xr, sr)))
    for p in items:
        if not os.path.exists(p):
            print('  (缺) %s' % p)
            continue
        x, sr2 = sf.read(p)
        if x.ndim > 1:
            x = x.mean(1)
        x = x / (np.max(np.abs(x)) or 1.0)
        e = {b: band_energy(x, sr2, *b) for b in BANDS}
        b0 = e[(250, 500)] + 1e-12
        print('%-30s' % os.path.basename(p)[:30] + ' ' +
              ' '.join('%6.1f' % (10 * np.log10(e[b] / b0)) for b in BANDS) +
              '   comb=%.2f  hfFlat=%.3f' % (comb_ratio(x, sr2), hf_flat(x, sr2)))


if __name__ == '__main__':
    main()
