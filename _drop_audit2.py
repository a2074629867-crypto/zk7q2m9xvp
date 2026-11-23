# -*- coding: utf-8 -*-
"""_drop_audit2.py —— 补三个原退化集没有的缺陷，并修两个测量 bug。

补：breathy（气声化，dots.tts 加 rate 标签的真实副作用）
    flat_slow（200ms 慢包络等响，比逐帧 flatamp 干净）
修：谱平坦度全 0（log(0)）；jitter 用 Praat call 取

输出 _drop_audit2.json
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _drop_audit import read, frame_db, pitch, energy_span, robust_f0  # noqa

PICK = "G:/_setup/_mt_pick"
UIDS = ["N0194", "N0239", "N0254", "N0552", "N0755"]


def flat_slow(x, sr, win=0.20):
    hop = int(0.01 * sr)
    n = int(win * sr)
    pad = np.pad(x, (n // 2, n // 2))
    k = 1 + (len(pad) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(k)[:, None]
    env = np.sqrt(np.mean(pad[idx] ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(env + 1e-9)
    p90 = np.percentile(db, 90)
    sp = db > p90 - 30
    if sp.sum() < 5:
        return x
    tgt = float(np.median(env[sp]))
    g = np.clip(tgt / np.maximum(env, 1e-9), 0.4, 2.5)
    w = np.hanning(31)
    w /= w.sum()
    g = np.convolve(np.pad(g, (15, 15), mode="edge"), w, "valid")
    acc = np.zeros(len(x))
    cnt = np.zeros(len(x))
    for i in range(k):
        a = i * hop
        b = min(a + hop, len(x))
        acc[a:b] += g[i]
        cnt[a:b] += 1
    return (x * (acc / np.maximum(cnt, 1))).astype(np.float32)


def breathy(x, sr, a=0.35):
    """气声化：混入高通白噪，模仿 <rate> 拉低后模型填气的效果。"""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(5)
    nz = rng.standard_normal(len(x)).astype(np.float32)
    sos = butter(4, 2000 / (sr / 2), btype="high", output="sos")
    hp = sosfilt(sos, nz).astype(np.float32)
    rms_x = np.sqrt(np.mean(x ** 2) + 1e-12)
    hp *= rms_x / (np.sqrt(np.mean(hp ** 2)) + 1e-12)
    return ((1 - a) * x + a * hp).astype(np.float32)


def spec(x, sr):
    import librosa
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256))
    fr = librosa.fft_frequencies(sr=sr, n_fft=1024)
    P = S ** 2
    tot = P.sum(0) + 1e-12
    m = tot >= np.quantile(tot, 0.60)
    P, T = P[:, m], tot[m]
    P = np.maximum(P, 1e-20)
    cen = float(np.median((fr[:, None] * P).sum(0) / T))
    lf = np.log2(np.maximum(fr[1:], 20.0))
    lp = 10 * np.log10(P[1:] + 1e-20)
    A = np.vstack([lf, np.ones_like(lf)])
    slope = float(np.median(np.linalg.lstsq(A.T, lp, rcond=None)[0][0]))
    flat = float(np.median(np.exp(np.mean(np.log(P), 0)) / np.mean(P, 0)))
    hi = fr >= 4000
    hf = float(np.median(P[hi].sum(0) / (P.sum(0) + 1e-20)))
    return dict(cent=cen, tilt=slope, flat=flat, hf=hf)


def hnr_of(x, sr):
    import parselmouth
    s = parselmouth.Sound(x, sampling_frequency=sr)
    h = s.to_harmonicity_cc()
    v = h.values[h.values > -100]
    return float(np.median(v)) if len(v) else None


def jitter_of(x, sr):
    import parselmouth
    s = parselmouth.Sound(x, sampling_frequency=sr)
    try:
        pp = parselmouth.praat.call(s, "To PointProcess (cc)")
        return float(parselmouth.praat.call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
    except Exception:
        return None


def meas(x, sr):
    db = frame_db(x, sr)
    f = pitch(x, sr)
    n = min(len(db), len(f))
    db, f = db[:n], f[:n]
    p90 = np.percentile(db, 90)
    sp_rel = (db > p90 - 25)
    sp_voi = sp_rel & (f > 0)

    def sp(M):
        if M.sum() < 42:
            return None
        seg = np.array_split(db[M], 21)
        pr = [np.percentile(s, 90) for s in seg]
        return float(max(pr) - min(pr))

    fv = robust_f0(f)
    d = dict(espan=sp(sp_rel), espan_v=sp(sp_voi),
             span_st=float(12 * np.log2(np.percentile(fv, 90) / np.percentile(fv, 10)))
             if len(fv) > 10 else None,
             hnr=hnr_of(x, sr), jitter=jitter_of(x, sr), **spec(x, sr))
    return d


def main():
    out = {"good": {}, "breathy": {}, "flat_slow": {}}
    for u in UIDS:
        x, sr = read(os.path.join(PICK, u + ".wav"))
        out["good"][u] = meas(x, sr)
        out["breathy"][u] = meas(breathy(x, sr), sr)
        out["flat_slow"][u] = meas(flat_slow(x, sr), sr)
    json.dump(out, open("G:/_setup/_drop_audit2.json", "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    keys = ["espan", "espan_v", "span_st", "hnr", "jitter", "cent", "tilt", "flat", "hf"]
    print("%-9s %-22s %-22s %-22s" % ("指标", "good p50", "breathy p50", "flat_slow p50"))
    for k in keys:
        g = [r[k] for r in out["good"].values() if r.get(k) is not None]
        b = [r[k] for r in out["breathy"].values() if r.get(k) is not None]
        s = [r[k] for r in out["flat_slow"].values() if r.get(k) is not None]
        f = lambda v: "%.3f" % np.median(v) if v else "-"
        print("%-9s %-22s %-22s %-22s" % (k, f(g), f(b), f(s)))


if __name__ == "__main__":
    main()
