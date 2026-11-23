# -*- coding: utf-8 -*-
"""逐段音色稳定性体检：F0 轨迹 + 频谱质心 + MFCC 段间一致性。

用途：找出"某一句音色炸了 / 换人了"的位置。整条声纹合格也可能是某一段跑偏。
用法：python ch123_stab.py a.wav b.wav ...
"""
import sys
import numpy as np
import soundfile as sf
import parselmouth
from parselmouth.praat import call

sys.path.insert(0, ".")
import ch123_rebuild as RB


def f0_track(x, sr, floor=70, ceil=450):
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil)
    f0 = pitch.selected_array["frequency"]
    f0[f0 <= 0] = np.nan
    return f0


def mfcc_mean(x, sr, n_mfcc=13):
    """不依赖 librosa：mel 滤波器组 + DCT。"""
    # 预加重
    y = np.append(x[0], x[1:] - 0.97 * x[:-1])
    n_fft, hop = 512, 160
    win = np.hamming(n_fft)
    frames = []
    for i in range(0, max(1, len(y) - n_fft), hop):
        fr = y[i:i + n_fft]
        if len(fr) < n_fft:
            fr = np.pad(fr, (0, n_fft - len(fr)))
        frames.append(np.abs(np.fft.rfft(fr * win)) ** 2)
    if not frames:
        return np.zeros(n_mfcc)
    P = np.array(frames)

    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700.0)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595.0) - 1)

    nfilt = 26
    lo, hi = hz2mel(80), hz2mel(min(sr / 2, 7600))
    pts = mel2hz(np.linspace(lo, hi, nfilt + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((nfilt, P.shape[1]))
    for m in range(1, nfilt + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        for k in range(l, min(c, P.shape[1])):
            fb[m - 1, k] = (k - l) / max(1, c - l)
        for k in range(c, min(r, P.shape[1])):
            fb[m - 1, k] = (r - k) / max(1, r - c)
    mel = np.log(P @ fb.T + 1e-10)
    # DCT-II
    N, M = mel.shape
    dct = np.zeros((N, n_mfcc))
    for k in range(n_mfcc):
        for n in range(M):
            dct[:, k] += mel[:, n] * np.cos(np.pi * k * (n + 0.5) / M)
    return dct.mean(0)


def centroid(x, sr):
    X = np.abs(np.fft.rfft(x * np.hamming(len(x)))) + 1e-10
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return float((X * f).sum() / X.sum())


def report(path, gap=0.12):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    segs = RB.split_at_silence(a, sr, min_gap=gap)
    f0 = f0_track(a, sr)
    rows = []
    print("\n=== %s  %.2fs  %d 段 ===" % (path, len(a) / sr, len(segs)))
    print("%-3s %6s %6s %6s %6s %6s %7s %6s" %
          ("#", "起-止", "时长", "dB", "F0中位", "F0跨度", "质心Hz", "抖动"))
    for i, (s0, s1) in enumerate(segs):
        seg = a[int(s0 * sr):int(s1 * sr)]
        i0, i1 = int(s0 / 0.01), int(s1 / 0.01)
        fs = f0[i0:i1]
        fs = fs[~np.isnan(fs)]
        med = float(np.median(fs)) if len(fs) else 0.0
        span = float(np.percentile(fs, 95) - np.percentile(fs, 5)) if len(fs) > 3 else 0.0
        # 抖动：相邻帧 F0 相对跳变的中位
        jit = 0.0
        if len(fs) > 3:
            d = np.abs(np.diff(fs)) / np.maximum(fs[1:], 1e-6)
            jit = float(np.median(d)) * 100
        rows.append(dict(i=i, t=(s0, s1), dur=s1 - s0,
                         db=RB.rms_voiced_db(seg, sr),
                         f0=med, span=span, cen=centroid(seg, sr), jit=jit,
                         mfcc=mfcc_mean(seg, sr)))
        print("%-3d %5.2f-%-5.2f %5.2fs %6.1f %6.0f %6.0f %7.0f %5.1f%%" %
              (i, s0, s1, s1 - s0, rows[-1]["db"], med, span, rows[-1]["cen"], jit))

    if len(rows) > 1:
        print("--- 段间一致性 ---")
        for i in range(1, len(rows)):
            p, q = rows[i - 1], rows[i]
            df0 = q["f0"] - p["f0"]
            dcen = (q["cen"] - p["cen"]) / max(p["cen"], 1)
            # MFCC 余弦相似度（去掉 c0 能量项）
            u, v = p["mfcc"][1:], q["mfcc"][1:]
            cs = float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
            flags = []
            if abs(df0) > 45:
                flags.append("F0跳%+.0fHz" % df0)
            if abs(dcen) > 0.18:
                flags.append("质心偏%+.0f%%" % (dcen * 100))
            if cs < 0.90:
                flags.append("MFCC %.3f" % cs)
            if q["jit"] > 8:
                flags.append("抖动%.1f%%" % q["jit"])
            print("  段%d→%d  ΔF0 %+6.0fHz  Δ质心 %+6.1f%%  MFCCcos %.3f  %s" %
                  (i - 1, i, df0, dcen * 100, cs,
                   "⚠ " + " / ".join(flags) if flags else "OK"))
    return rows


if __name__ == "__main__":
    for p in sys.argv[1:]:
        report(p)
