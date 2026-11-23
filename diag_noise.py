# -*- coding: utf-8 -*-
"""诊断底噪 + 电音 artifact。
用法: python diag_noise.py <wav> [<wav> ...]
指标:
  sr        采样率(电音第一嫌疑: 24k/32k/44.1k 标注错误会变调+电音)
  floor_db  底噪(能量最低 5% 帧的 RMS, dBFS) —— 越低越干净
  snr_db    语音段/底噪段 能量比
  flat      谱平坦度中位(几何均/算术均) —— 电音/噪声会让它升高(纯音~0, 白噪~1)
  hf_ratio  >8kHz 能量占比 —— 声码器高频 artifact 常在这里堆积
  hnr       谐噪比 —— 电音会降低周期性
  jitter    帧间谱通量的抖动(PSOLA/声码器不连续会抬高)
"""
import sys, os
import numpy as np
import soundfile as sf
import librosa


def db(x):
    return 20 * np.log10(max(float(x), 1e-12))


def analyze(path):
    x, sr = sf.read(path, always_2d=False)
    if x.ndim > 1:
        x = x.mean(1)
    x = np.asarray(x, dtype=np.float64)
    dur = len(x) / sr
    # 归一到 -3dBFS 峰值，避免音量差干扰比较
    pk = np.max(np.abs(x)) or 1.0
    xn = x / pk * 0.7

    # 帧能量
    fl = int(0.025 * sr)
    hop = int(0.010 * sr)
    n = 1 + max(0, (len(xn) - fl) // hop)
    frames = np.stack([xn[i * hop:i * hop + fl] for i in range(n)]) if n > 0 else xn[None, :]
    rms = np.sqrt((frames ** 2).mean(1) + 1e-12)
    rdb = 20 * np.log10(rms + 1e-12)

    floor = np.percentile(rdb, 5)
    voice = np.percentile(rdb, 75)
    snr = voice - floor

    # 谱平坦度 + 高频比 + 谱通量
    S = np.abs(librosa.stft(xn, n_fft=1024, hop_length=256)) + 1e-10
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    # 只统计语音带 100-8000Hz 的平坦度(排除极低频/极高频偏置)
    band = (freqs >= 100) & (freqs <= 8000)
    Sb = S[band]
    flat = np.median(np.exp(np.mean(np.log(Sb), axis=0)) / (np.mean(Sb, axis=0) + 1e-12))
    hf = (S[freqs >= 8000] ** 2).sum() / ((S ** 2).sum() + 1e-12)

    # HNR: 自相关在基频滞后处的峰值 / 其余
    hnr = _hnr(xn, sr)

    # 谱通量抖动: 相邻帧谱通量的标准差 / 均值(电音→周期性跳变→抖动大)
    flux = np.sqrt(((np.diff(S, axis=1)) ** 2).sum(0))
    jit = float(np.std(flux) / (np.mean(flux) + 1e-12))

    return dict(sr=sr, dur=dur, floor=float(floor), snr=float(snr),
                flat=float(flat), hf=float(hf), hnr=float(hnr), jit=jit)


def _hnr(x, sr, fmin=60, fmax=400):
    """简化 HNR: 取语音最强的 20 帧，算自相关峰值比。"""
    fl = int(0.040 * sr)
    hop = int(0.020 * sr)
    n = max(1, (len(x) - fl) // hop)
    best = []
    for i in range(n):
        fr = x[i * hop:i * hop + fl]
        if len(fr) < fl:
            break
        e = np.sqrt((fr ** 2).mean())
        if e < 1e-4:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, 'full')[len(fr) - 1:]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(ac):
            continue
        pk = ac[lo:hi].max() if hi > lo else 0.0
        best.append((e, pk))
    if not best:
        return 0.0
    best.sort(reverse=True)
    return float(np.mean([p for _, p in best[:20]]))


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return
    print('%-34s %7s %6s %8s %7s %7s %7s %7s' %
          ('文件', 'sr', '时长', '底噪dB', 'SNR', '平坦度', '高频比', 'HNR', ))
    print('-' * 100)
    for p in paths:
        if not os.path.exists(p):
            print('  (缺) %s' % p)
            continue
        try:
            r = analyze(p)
        except Exception as e:
            print('  ERR %s: %s' % (os.path.basename(p), e))
            continue
        print('%-34s %6d %5.1fs %8.1f %7.1f %7.4f %6.1f%% %7.3f' %
              (os.path.basename(p)[:34], r['sr'], r['dur'], r['floor'],
               r['snr'], r['flat'], r['hf'] * 100, r['hnr']))


if __name__ == '__main__':
    main()
