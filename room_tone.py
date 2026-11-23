# -*- coding: utf-8 -*-
"""room_tone.py —— 给（被静音保护清空的）停顿段铺回环境底噪。

【问题】实测：
  - GPT-SoVITS 生成端：静音段 = 绝对数字零（-199.9 dB），语音段底噪 ≈ -56.4 dB
  - 马修真人原声：**没有任何"静音帧"（0%）**，整段都有 -55.9 dB 底噪
  ⇒ 静音保护把停顿做成绝对零后，听感 = 「一会儿有底噪、一会儿没有」。
  ⇒ 修法：把停顿段填成与语音段底噪同电平的 room tone（环境底噪）。

【做法】
  1. 从长录音中挑选低于阈值的安静帧，统计其中位噪声频谱；绝不能直接铺含语音的最低连续窗口
  2. 随机相位合成足够长的无词句噪声床，按指定电平归一化（建议先听 -57dB 档）
  3. 混合：--mode all（整段叠加，最自然）或 silence（仅填检测到的静音段）

【用法】
  # 提取 room tone
  python -u room_tone.py --extract --src real.wav --tone room.wav --dur 3.0
  # 应用
  python -u room_tone.py --in X.wav --out Y.wav --tone room.wav --level-db -58
  # 自动匹配输入语音段底噪
  python -u room_tone.py --in X.wav --out Y.wav --tone room.wav --match
"""
import argparse
import os
from math import gcd

import numpy as np
import soundfile as sf


def _rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2) + 1e-20))


def _db(x):
    return 20 * np.log10(_rms(x) + 1e-12)


def _resample(x, sr_in, sr_out):
    if int(sr_in) == int(sr_out):
        return x
    from scipy.signal import resample_poly
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(x, int(sr_out) // g, int(sr_in) // g)


def _frame_db(x, sr, fl=0.02, hop=0.01):
    fl_n = max(1, int(fl * sr))
    hop_n = max(1, int(hop * sr))
    n = max(1, (len(x) - fl_n) // hop_n + 1)
    idx = np.arange(fl_n)[None, :] + hop_n * np.arange(n)[:, None]
    np.clip(idx, 0, len(x) - 1, out=idx)
    r = np.sqrt((x[idx] ** 2).mean(1) + 1e-20)
    return 20 * np.log10(r + 1e-12)


def voice_floor_db(x, sr):
    """估计非纯静音的低能量帧；仅供参考，不能当作真实底噪。"""
    db = _frame_db(x, sr)
    candidate = db[(db > -75) & (db < -42)]
    return float(np.percentile(candidate, 25)) if len(candidate) >= 10 else -56.0


def extract(src, tone_out, dur=4.0, fl=0.04, quiet_db=-49.0, seed=2026):
    """从长录音的安静帧估计噪声频谱，随机相位合成无词句的 room tone。"""
    from scipy.signal import welch
    rng = np.random.default_rng(seed)
    spectra = []
    with sf.SoundFile(src) as f:
        sr = f.samplerate
        frame = max(256, int(fl * sr))
        for block in f.blocks(blocksize=sr * 12, dtype='float64'):
            if block.ndim > 1:
                block = block.mean(axis=1)
            count = len(block) // frame
            if count == 0:
                continue
            windows = block[:count * frame].reshape(count, frame)
            db = 20 * np.log10(np.sqrt(np.mean(windows * windows, axis=1) + 1e-20) + 1e-12)
            quiet = windows[db <= quiet_db]
            if len(quiet):
                for q in quiet[::max(1, len(quiet) // 20)][:20]:
                    _, power = welch(q, fs=sr, nperseg=min(1024, frame), nfft=2048)
                    spectra.append(power)
    if len(spectra) < 30:
        raise ValueError('原声的安静帧不足（%d 帧），无法提取无语音的噪声频谱' % len(spectra))
    psd = np.median(np.asarray(spectra), axis=0)
    n = int(dur * sr)
    freq = np.fft.rfftfreq(n, 1.0 / sr)
    shape = np.sqrt(np.interp(freq, np.linspace(0, sr / 2, len(psd)), psd))
    shape[freq < 65] = 0
    phase = rng.uniform(0, 2 * np.pi, len(shape))
    tone = np.fft.irfft(shape * np.exp(1j * phase), n)
    tone = tone / _rms(tone) * 10 ** (-56 / 20)
    sf.write(tone_out, tone, sr, subtype='FLOAT')
    print('[ok] 噪声频谱: %d 个安静帧，合成 %.2fs @ %dHz RMS %.1fdB（随机相位，无原声词句）'
          % (len(spectra), dur, sr, _db(tone)), flush=True)
    return tone_out


def _bed(n, sr, tone, fade_ms=50):
    """加窗平铺 tone 成 n 样本的噪声床（重叠区两窗互补，和为 1）。"""
    L = len(tone)
    fade = min(max(1, int(fade_ms / 1000.0 * sr)), max(1, L // 2))
    w = np.ones(L)
    w[:fade] = np.linspace(0.0, 1.0, fade)
    w[-fade:] = np.linspace(1.0, 0.0, fade)
    hop = max(1, L - fade)
    out = np.zeros(n + L)
    pos = 0
    while pos < n:
        out[pos:pos + L] += tone * w
        pos += hop
    return out[:n]


def apply(inp, outp, tone_path, level_db=None, mode='all',
          silence_floor_db=-52.0, fade_ms=50, auto_match=True):
    x, sr = sf.read(inp)
    if x.ndim > 1:
        x = x.mean(1)
    x = np.asarray(x, dtype=np.float64)

    tone, tsr = sf.read(tone_path)
    if tone.ndim > 1:
        tone = tone.mean(1)
    tone = np.asarray(tone, dtype=np.float64)
    tone = _resample(tone, tsr, sr)

    vf = voice_floor_db(x, sr)
    target = vf if (level_db is None and auto_match) else (level_db if level_db is not None else -58.0)
    if len(tone) < max(100, int(.2 * sr)) or _rms(tone) < 1e-8:
        raise ValueError('room tone 太短或没有可用噪声')
    tone = tone / _rms(tone) * (10.0 ** (target / 20.0))

    bed = _bed(len(x), sr, tone, fade_ms=fade_ms)

    if mode == 'silence':
        db = _frame_db(x, sr)
        sil_frame = db < silence_floor_db
        hop_n = max(1, int(0.01 * sr))
        m = np.repeat(sil_frame, hop_n)[:len(x)]
        if len(m) < len(x):
            m = np.pad(m, (0, len(x) - len(m)), constant_values=False)
        k = max(1, int(0.02 * sr))
        m = np.convolve(m.astype(np.float64), np.ones(k) / k, mode='same')
        y = x + bed * m
    else:
        y = x + bed

    pk = float(np.abs(y).max())
    if pk > 0.999:
        y = y / pk * 0.999

    sf.write(outp, y, sr)
    return dict(target_db=target, voice_floor_db=vf,
                in_p05=float(np.percentile(_frame_db(x, sr), 5)),
                out_p05=float(np.percentile(_frame_db(y, sr), 5)),
                mode=mode, dur=len(x) / sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--extract', action='store_true')
    ap.add_argument('--src')
    ap.add_argument('--tone')
    ap.add_argument('--dur', type=float, default=40.0)
    ap.add_argument('--in', dest='inp')
    ap.add_argument('--out', dest='outp')
    ap.add_argument('--level-db', type=float, default=None)
    ap.add_argument('--match', action='store_true', help='自动匹配输入音频的语音段底噪')
    ap.add_argument('--mode', default='all', choices=['all', 'silence'])
    ap.add_argument('--fade-ms', type=float, default=50.0)
    a = ap.parse_args()

    if a.extract:
        extract(a.src, a.tone, a.dur)
        return

    r = apply(a.inp, a.outp, a.tone, level_db=a.level_db, mode=a.mode,
              fade_ms=a.fade_ms, auto_match=a.match or (a.level_db is None))
    print('[ok] %s | mode=%s | 目标底噪 %.1f dB（语音段底噪 %.1f）| p05 %.1f -> %.1f dB | %.2fs -> %s'
          % (os.path.basename(a.inp), r['mode'], r['target_db'], r['voice_floor_db'],
             r['in_p05'], r['out_p05'], r['dur'], os.path.basename(a.outp)), flush=True)


if __name__ == '__main__':
    main()
