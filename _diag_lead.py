# -*- coding: utf-8 -*-
"""判定 clean118 产物开头的 1.4s 到底是「参考泄漏」还是「wav2vec2 幻觉」

三条独立证据：
1) 波形互相关：如果和参考某段高度相关（>0.5），说明是复制/泄漏
2) 谱质心/基频：真语音有清晰 F0 谐波结构，幻觉通常是噪声/混响
3) 单独 ASR：把 0~1.5s 切出来单独跑 wav2vec2，看是否输出稳定词串
"""
import os
import sys
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

ROOT = "G:/_setup"


def rd(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


def xcorr_best(seg, ref):
    """返回 seg 在 ref 中滑动的最佳归一化相关系数与位置"""
    s = seg - seg.mean()
    r = ref - ref.mean()
    n = len(s) + len(r) - 1
    nfft = 1 << (n - 1).bit_length()
    c = fftconvolve(r, s[::-1], mode="full")
    c = c[len(s) - 1:len(r)]          # 只保留合法起点
    # 归一化：局部能量
    e = np.concatenate([[0], np.cumsum(r ** 2)])
    win = e[len(s):] - e[:-len(s)]
    denom = np.sqrt(win * (s ** 2).sum()) + 1e-12
    cc = c / denom
    i = int(np.argmax(np.abs(cc)))
    return float(cc[i]), i


def f0_track(y, sr, fmin=70, fmax=400):
    """用自相关测每帧 F0 与 voiced 比例"""
    hop = int(0.02 * sr)
    win = int(0.04 * sr)
    n = 1 + (len(y) - win) // hop
    f0s = []
    for i in range(n):
        fr = y[i * hop:i * hop + win]
        if np.sqrt((fr ** 2).mean()) < 1e-4:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[win - 1:]
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(ac):
            continue
        seg = ac[lo:hi]
        j = int(np.argmax(seg)) + lo
        if ac[0] > 0 and ac[j] / ac[0] > 0.3:
            f0s.append(sr / j)
    return np.array(f0s)


def spec_flat(y, sr):
    """谱平坦度：噪声接近 1，浊音很低"""
    fr = y[:int(0.04 * sr)]
    if len(fr) < 128:
        return 1.0
    S = np.abs(np.fft.rfft(fr * np.hanning(len(fr)))) + 1e-12
    return float(np.exp(np.mean(np.log(S))) / np.mean(S))


def main():
    rid = sys.argv[1] if len(sys.argv) > 1 else "c1_0002"
    new = os.path.join(ROOT, "_sweep/clean118/%s__s42.wav" % rid)
    old = os.path.join(ROOT, "_audio_ch123/out/%s.wav" % rid)
    refs = [("_ref9_clean/Joseph_normal.wav", os.path.join(ROOT, "_ref9_clean/Joseph_normal.wav")),
            ("_ref9/Joseph_normal.wav", os.path.join(ROOT, "_ref9/Joseph_normal.wav"))]

    a, sr = rd(new)
    b, _ = rd(old)
    print("== 文件 ==")
    for p, y in ((new, a), (old, b)):
        print("  %-46s %.2fs  peak %.2f  voicedRMS %.1f"
              % (os.path.basename(p), len(y) / sr, np.abs(y).max(),
                 np.mean([20 * np.log10(np.sqrt((y[i:i + 960] ** 2).mean()) + 1e-12)
                          for i in range(0, len(y) - 960, 480)
                          if 20 * np.log10(np.sqrt((y[i:i + 960] ** 2).mean()) + 1e-12) > -45])))

    seg = a[:int(1.5 * sr)]
    print("\n== 证据1 波形互相关（clean118 开头 1.5s 在参考里找）==")
    for name, p in refs:
        if not os.path.exists(p):
            continue
        r, _sr = rd(p)
        cc, pos = xcorr_best(seg, r)
        print("  vs %-16s corr %+.3f  at %.2fs（参考长 %.2fs）" % (name, cc, pos / sr, len(r) / sr))

    print("\n== 证据2 F0 与谱平坦度（真语音 vs 噪声/混响）==")
    for lbl, y0 in (("clean118 开头1.5s", a[:int(1.5 * sr)]),
                    ("clean118 正文2.5-4.5s", a[int(2.5 * sr):int(4.5 * sr)]),
                    ("现用版开头1.5s", b[:int(1.5 * sr)]),
                    ("ref9_clean 末1.5s", rd(refs[0][1])[0][-int(1.5 * sr):]),
                    ("ref9 末1.5s", rd(refs[1][1])[0][-int(1.5 * sr):])):
        f0 = f0_track(y0, sr)
        print("  %-24s F0 n=%3d 中位 %.0fHz  跨度 %.0f~%.0f  谱平坦度 %.4f"
              % (lbl, len(f0), np.median(f0) if len(f0) else 0,
                 f0.min() if len(f0) else 0, f0.max() if len(f0) else 0, spec_flat(y0, sr)))

    # 证据3：切出来单独存，方便直接试听
    outs = os.path.join(ROOT, "_diag_lead")
    os.makedirs(outs, exist_ok=True)
    for tag, y0 in (("head", a[:int(1.5 * sr)]), ("body", a[int(2.3 * sr):]),
                    ("old_head", b[:int(1.5 * sr)])):
        sf.write(os.path.join(outs, "%s_%s.wav" % (rid, tag)), y0, sr)
    print("\n已切出试听片段 → %s" % outs)


if __name__ == "__main__":
    main()
