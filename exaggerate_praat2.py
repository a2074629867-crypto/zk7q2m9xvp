# -*- coding: utf-8 -*-
"""F0 夸张化 v2 —— 带静音段保护 + 噪声门 + 可选高频抑制。

v1 的问题（实测）：
  底噪 -120dB → -67dB，HNR 0.580 → 0.61。
  k=1.0（完全不改 F0）也一样 ⇒ 底噪与 HNR 恶化**全部来自 Praat 的 overlap-add 重合成本身**。

v2 的修法：
  ① **静音段保护**：重合成后，把原始能量极低的区段恢复成原始样本（真静音=数字 0）。
     交叉淡化 10ms 避免咔哒。→ 底噪回落到 -100dB 以下。
  ② **噪声门**（可选）：对全段低于阈值的帧做平滑衰减，进一步压底噪。
  ③ **高频抑制**（可选）：声码器在 2–8kHz 比原声高 3–7dB，用温和 shelf 压回来。

用法：
  python -u exaggerate_praat2.py --in X.wav --out Y.wav --ks 1.3,1.6 [--noise-gate -50] [--hf-tame 1.5]
"""
import argparse
import os

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call


def _frame_rms(x, sr, fl=0.02, hop=0.01):
    fl_n = max(1, int(fl * sr))
    hop_n = max(1, int(hop * sr))
    n = max(1, (len(x) - fl_n) // hop_n + 1)
    idx = np.arange(fl_n)[None, :] + hop_n * np.arange(n)[:, None]
    np.clip(idx, 0, len(x) - 1, out=idx)
    fr = x[idx]
    return np.sqrt((fr ** 2).mean(1) + 1e-20), fl_n, hop_n


def _frames_to_samples(m, fl_n, hop_n, total):
    """帧级布尔 → 样本级布尔（向量化）。"""
    idx = np.flatnonzero(m)
    if len(idx) == 0:
        return np.zeros(total, dtype=bool)
    starts = idx * hop_n
    ends = np.minimum(total, starts + fl_n)
    delta = np.zeros(total + 1, dtype=np.int32)
    np.add.at(delta, starts, 1)
    np.add.at(delta, ends, -1)
    return np.cumsum(delta[:-1]) > 0


def _silence_mask(x, sr, floor_db=-52.0, min_run=0.08):
    """返回逐样本布尔：True = 静音（可安全恢复原始）。"""
    r, fl_n, hop_n = _frame_rms(x, sr)
    db = 20 * np.log10(r + 1e-12)
    peak = np.percentile(db, 95)
    m = db < (peak + floor_db)          # 比语音峰值低 52dB 以上算静音
    # 抹掉短于 min_run 的孤立段（避免切碎语音里的停顿）
    run = int(min_run / 0.01)
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < run:
                m[i:j] = False
            i = j
        else:
            i += 1
    # 帧级 → 样本级
    return _frames_to_samples(m, fl_n, hop_n, len(x))


def _crossfade_restore(resyn, orig, mask, sr, fade_ms=10):
    """在 mask 为 True 的区段用 orig 替换 resyn，边界做交叉淡化。"""
    out = resyn.copy()
    n = len(out)
    if not mask.any():
        return out
    fade = max(1, int(fade_ms / 1000.0 * sr))
    # 找连通段
    idx = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(np.int8)))
    for s, e in zip(idx[0::2], idx[1::2]):
        a = max(0, s - fade)
        b = min(n, e + fade)
        seg_len = b - a
        w = np.ones(seg_len)
        # 段内全用 orig，两侧 fade 长度内线性过渡
        lf = min(fade, seg_len)
        w[:lf] = np.linspace(0, 1, lf)
        w[-lf:] = np.linspace(1, 0, lf)
        out[a:b] = w * orig[a:b] + (1 - w) * resyn[a:b]
    return out


def _noise_gate(x, sr, thresh_db=-50.0, floor_gain=0.0):
    """软噪声门：低于阈值的帧按比例衰减到 floor_gain。"""
    r, fl_n, hop_n = _frame_rms(x, sr)
    db = 20 * np.log10(r + 1e-12)
    gain = np.ones(len(db))
    below = db < thresh_db
    # 平滑过渡 6dB
    t = np.clip((thresh_db + 6 - db) / 6.0, 0.0, 1.0)
    gain = 1.0 - t * (1.0 - floor_gain)
    # 帧增益上采样到样本
    gs = np.repeat(gain, hop_n)[:len(x)]
    if len(gs) < len(x):
        gs = np.pad(gs, (0, len(x) - len(gs)), constant_values=float(gain[-1]))
    # 轻度平滑避免呼吸感
    k = max(1, int(0.01 * sr))
    gs = np.convolve(gs, np.ones(k) / k, mode='same')
    return x * gs


def exaggerate(in_wav, out_wav, k=1.4, floor=60.0, ceil=400.0, period=0.01,
               protect_silence=True, silence_floor_db=-52.0,
               noise_gate=None, hf_tame=0.0):
    x, sr = sf.read(in_wav)
    if x.ndim > 1:
        x = x.mean(1)
    x = np.asarray(x, dtype=np.float64)

    snd = parselmouth.Sound(in_wav)
    manip = call(snd, "To Manipulation", period, floor, ceil)
    pt = call(manip, "Extract pitch tier")
    n = int(call(pt, "Get number of points"))
    if n < 5:
        raise RuntimeError("pitch tier 点数过少: %d" % n)
    vals = np.array([call(pt, "Get value at index", i + 1) for i in range(n)], dtype=float)
    med = float(np.median(vals))
    if abs(k - 1.0) > 1e-6:
        call(pt, "Formula", "if self > 0 then %.8f * (self / %.8f) ^ %.4f else 0 fi" % (med, med, k))
    call([pt, manip], "Replace pitch tier")
    out_snd = call(manip, "Get resynthesis (overlap-add)")
    y = np.asarray(out_snd.values, dtype=np.float64)
    if y.ndim > 1:
        y = y[0]
    # 对齐长度
    L = min(len(x), len(y))
    x, y = x[:L], y[:L]

    # ① 静音段保护
    if protect_silence:
        mask = _silence_mask(x, sr, floor_db=silence_floor_db)
        y = _crossfade_restore(y, x, mask, sr)

    # ② 噪声门
    if noise_gate is not None:
        y = _noise_gate(y, sr, thresh_db=noise_gate)

    # ③ 高频温和抑制（2-8kHz 堆积）
    if hf_tame > 0:
        try:
            from scipy.signal import butter, sosfilt
            nyq = sr / 2.0
            hi = min(0.92, 8000.0 / nyq)
            lo = min(0.88, 2000.0 / nyq)
            if hi > lo:
                sos = butter(2, [lo, hi], btype='band', output='sos')
                band = sosfilt(sos, y)
                y = y - band * float(hf_tame)
        except Exception as e:
            print('  [warn] hf_tame 失败: %s' % e)

    sf.write(out_wav, y, sr)
    return n, med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out", dest="outp")
    ap.add_argument("--in-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--ks", default="1.4")
    ap.add_argument("--no-protect", action="store_true", help="关闭静音段保护（对照用）")
    ap.add_argument("--noise-gate", type=float, default=None, help="噪声门阈值 dBFS")
    ap.add_argument("--hf-tame", type=float, default=0.0, help="2-8kHz 抑制强度 0~1")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    ks = [float(v) for v in a.ks.split(",") if v]
    protect = not a.no_protect

    if a.inp:
        for k in ks:
            out = a.outp if len(ks) == 1 else a.outp.replace(".wav", "_k%02d.wav" % int(round(k * 10)))
            n, med = exaggerate(a.inp, out, k, protect_silence=protect,
                                noise_gate=a.noise_gate, hf_tame=a.hf_tame)
            print("[ok] k=%.2f pts=%d med=%.1fHz protect=%s -> %s"
                  % (k, n, med, protect, os.path.basename(out)), flush=True)
        return

    os.makedirs(a.out_dir, exist_ok=True)
    for f in sorted(x for x in os.listdir(a.in_dir) if x.endswith(".wav")):
        for k in ks:
            out = os.path.join(a.out_dir, "%s%s_k%02d.wav" % (f[:-4], a.suffix, int(round(k * 10))))
            try:
                n, med = exaggerate(os.path.join(a.in_dir, f), out, k,
                                    protect_silence=protect,
                                    noise_gate=a.noise_gate, hf_tame=a.hf_tame)
                print("[ok] %-14s k=%.2f pts=%4d med=%.1f -> %s" % (f, k, n, med, os.path.basename(out)), flush=True)
            except Exception as e:
                print("[!!] %s k=%.2f 失败: %s" % (f, k, e), flush=True)


if __name__ == "__main__":
    main()
