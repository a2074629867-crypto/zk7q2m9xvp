# -*- coding: utf-8 -*-
"""L078 'No. But...' 的自然拖音。

用户要求：省略号 = 拖音，要自然延长，不是机械拉伸整段。

原 But 段结构（0.73-0.96）：
    /b/ 爆破  0.73-0.75
    /ʌ/ 元音  0.75-0.88  (0.13s)
    /t/ 收尾  0.88-0.96

做法：只对元音做 OLA 时间拉伸（音高/共振峰不变），/b/ 和 /t/ 原样保留，
      末尾加轻微渐弱模拟气息，不硬收。
"""
import os
import numpy as np
import soundfile as sf

SRC = "ch123/L078.wav"
OUT = "ch123_clean/L078.wav"
NO_END = 0.390      # "No." 结束
GAP = 0.34          # No. 与 But 之间停顿
B0, V0, V1, T1 = 0.730, 0.752, 0.884, 0.958   # But 各部件边界


def ola_stretch(x, factor, n_fft=1024, hop=256):
    """Overlap-add 时间拉伸（保音高）。factor>1 = 变长。"""
    win = np.hanning(n_fft).astype(np.float32)
    hop_out = int(round(hop * factor))
    n_out = int(len(x) * factor) + n_fft
    y = np.zeros(n_out, dtype=np.float32)
    wsum = np.zeros(n_out, dtype=np.float32)
    src_pos = 0.0
    out_pos = 0
    while src_pos + n_fft < len(x):
        i = int(src_pos)
        y[out_pos:out_pos + n_fft] += x[i:i + n_fft] * win
        wsum[out_pos:out_pos + n_fft] += win
        src_pos += hop
        out_pos += hop_out
    wsum[wsum < 1e-6] = 1.0
    y /= wsum
    return y[:int(len(x) * factor)]


def fade(x, sr, ms_in=8, ms_out=20, out_gain=1.0):
    x = x.copy()
    a = int(ms_in / 1000 * sr)
    b = int(ms_out / 1000 * sr)
    if a > 0:
        x[:a] *= np.linspace(0, 1, a)
    if b > 0 and b < len(x):
        # 末尾渐弱到 out_gain，模拟气息收尾
        x[-b:] *= np.linspace(1.0, out_gain, b)
    return x


def build(vowel_target, out_gain, tail_ms, tag):
    a, sr = sf.read(SRC, dtype="float32", always_2d=True)
    a = a.mean(1)

    no = a[:int(NO_END * sr)].copy()
    b = a[int(B0 * sr):int(V0 * sr)].copy()          # /b/
    v = a[int(V0 * sr):int(V1 * sr)].copy()          # /ʌ/
    t = a[int(V1 * sr):int(T1 * sr)].copy()          # /t/

    factor = vowel_target / (len(v) / sr)
    vv = ola_stretch(v, factor)
    vv = fade(vv, sr, ms_in=10, ms_out=10)
    # 元音整体轻微渐弱（拖音通常越来越轻）
    env = np.linspace(1.0, out_gain, len(vv)).astype(np.float32)
    vv *= env

    but = np.concatenate([fade(b, sr, 4, 4), vv, fade(t, sr, 4, 8)])
    gap = np.zeros(int(GAP * sr), dtype=np.float32)
    tail = np.zeros(int(tail_ms / 1000 * sr), dtype=np.float32)
    y = np.concatenate([fade(no, sr, 6, 6), gap, but, tail])

    # 统一电平
    import sys
    sys.path.insert(0, ".")
    import ch123_clean as CL
    y = CL.clean(y, sr)
    sf.write(OUT, y, sr, subtype="PCM_16")
    print("%-10s 元音 %.2fs→%.2fs (×%.2f)  总 %.2fs  末尾增益 %.2f"
          % (tag, len(v) / sr, len(vv) / sr, factor, len(y) / sr, out_gain))


if __name__ == "__main__":
    # A: 元音拉到 0.35s，保留 /t/，轻微渐弱
    build(0.35, 0.72, 60, "A")
    sf.write("_l078_A.wav", sf.read(OUT)[0], sr := sf.read(OUT)[1], subtype="PCM_16")
    # B: 元音 0.45s，更明显的拖
    build(0.45, 0.62, 80, "B")
    sf.write("_l078_B.wav", sf.read(OUT)[0], sr, subtype="PCM_16")
    # C: 元音 0.35s，几乎不渐弱（更实）
    build(0.35, 0.88, 60, "C")
    sf.write("_l078_C.wav", sf.read(OUT)[0], sr, subtype="PCM_16")
    # 恢复默认到 A
    build(0.35, 0.72, 60, "final")
