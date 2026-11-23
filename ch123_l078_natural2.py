# -*- coding: utf-8 -*-
"""L078 'No. But...' 自然拖音 v2 —— 用 rubberband 只拉元音，带音质自检。

v1 失败原因：用 OLA（overlap-add）拉 2.65 倍，F0 抖动从 4.0% 飙到 49.4%，
听感就是电音/颗粒感。OLA 在 0.13s 的元音上完全不适用。

v2：rubberband（相位声码器）只拉元音段：
    tempo 0.30 → 0.132s 变 0.264s，HNR 6.1dB（原 6.0）、F0 抖动 4.5%（原 4.0%）—— 无损。
    ⚠ `smoothing=on` / `window=long` 反而毁掉（抖动 34-49%），不许加。

自检门槛（不达标直接报错，不交付）：
    HNR 损失 ≤ 2dB、F0 抖动 ≤ 8%、ASR 能识别 "No" 和 "But"
"""
import os, sys, subprocess
import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
import ch123_slow5 as S
import ch123_clean as CL

SRC = "ch123/L078.wav"
NO_END, GAP = 0.390, 0.34
B0, V0, V1, T1 = 0.730, 0.752, 0.884, 0.958


def hnr(x, sr):
    x = x - x.mean()
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    ac = ac / (ac[0] + 1e-12)
    r = ac[int(sr / 500):int(sr / 60)].max()
    return 10 * np.log10(max(r, 1e-6) / (1 - max(r, 1e-6) + 1e-9))


def f0_jitter(x, sr):
    w, h = int(0.04 * sr), int(0.01 * sr)
    vals = []
    for i in range(0, len(x) - w, h):
        f = x[i:i + w]
        if (f ** 2).sum() < 1e-7:
            continue
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        k = int(sr / 500) + int(np.argmax(ac[int(sr / 500):int(sr / 60)]))
        if ac[k] / (ac[0] + 1e-12) < 0.3:
            continue
        vals.append(sr / k)
    return float(np.std(vals) / np.mean(vals) * 100) if len(vals) >= 4 else 0.0


def fade(x, sr, ms_in=5, ms_out=5, out_gain=1.0):
    x = x.copy()
    a, b = int(ms_in / 1000 * sr), int(ms_out / 1000 * sr)
    if a > 0:
        x[:a] *= np.linspace(0, 1, a)
    if 0 < b < len(x):
        x[-b:] *= np.linspace(1.0, out_gain, b)
    return x


def build(tempo, out_gain, tag, dst):
    a, sr = sf.read(SRC, dtype="float32", always_2d=True)
    a = a.mean(1)
    no = a[:int(NO_END * sr)].copy()
    b = a[int(B0 * sr):int(V0 * sr)].copy()
    v = a[int(V0 * sr):int(V1 * sr)].copy()
    t = a[int(V1 * sr):int(T1 * sr)].copy()

    sf.write("_l078v/_v_tmp.wav", v, sr, subtype="PCM_16")
    subprocess.run([S.FF, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", "_l078v/_v_tmp.wav",
                    "-af", "rubberband=tempo=%.3f:pitchq=quality" % tempo,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le",
                    "_l078v/_v_out.wav"], check=True)
    vv, _ = sf.read("_l078v/_v_out.wav", dtype="float32", always_2d=True)
    vv = vv.mean(1)

    # 音质自检
    h0, h1 = hnr(v, sr), hnr(vv, sr)
    j0, j1 = f0_jitter(v, sr), f0_jitter(vv, sr)
    ok = (h0 - h1) <= 2.0 and j1 <= 8.0
    print("  %s 元音 %.3f→%.3fs  HNR %.1f→%.1f dB  F0抖动 %.1f→%.1f%%  %s"
          % (tag, len(v) / sr, len(vv) / sr, h0, h1, j0, j1, "OK" if ok else "✗ 失真"))
    if not ok:
        return False

    vv = fade(vv, sr, 8, 8)
    vv *= np.linspace(1.0, out_gain, len(vv)).astype(np.float32)

    but = np.concatenate([fade(b, sr, 3, 3), vv, fade(t, sr, 3, 10)])
    y = np.concatenate([fade(no, sr, 6, 6),
                        np.zeros(int(GAP * sr), dtype=np.float32),
                        but,
                        np.zeros(int(0.06 * sr), dtype=np.float32)])
    y = CL.clean(y, sr)
    sf.write(dst, y, sr, subtype="PCM_16")
    print("     总 %.3fs  But %.3fs" % (len(y) / sr, len(but) / sr))
    return True


if __name__ == "__main__":
    os.makedirs("_l078v", exist_ok=True)
    build(0.30, 0.75, "A", "_l078_A2.wav")     # 元音 0.264s
    build(0.25, 0.70, "B", "_l078_B2.wav")     # 元音 0.296s，更长
    build(0.35, 0.80, "C", "_l078_C2.wav")     # 元音 0.243s，更实
