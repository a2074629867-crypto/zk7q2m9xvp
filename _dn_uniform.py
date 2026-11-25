# -*- coding: utf-8 -*-
"""_dn_uniform.py —— 全库统一除噪（谱减 + 门限），语音不动、底噪统一。

为什么不用 arnndn / rnnoise：那类 RNN 除噪会连气声、弱辅音一起吃掉，
2026-11-22 实测 10 条里 2 条吃字。这里的做法只改**非语音部分**和
**稳态噪声的谱**，语音谐波几乎不动，所以不吃字。

为什么 _denoise_floor.py 的 gate 对 c2_0299 无效：那条底噪 −48 dBFS，
比「峰值−40dB」的阈值还高，被判成语音，一点没降（实测 −48 → −48）。

三步：
1. 逐频点分位估计稳态噪声谱 N（持续噪声：15 分位；语音是时变的，分位会偏低）
2. 幅度谱减（Wiener），增益下限 gmin 防音乐噪声，时间轴一阶平滑
3. 残留底噪统一到 target_floor（默认 −72 dBFS 白噪），不用绝对零 ——
   绝对零和 −72 dB 之间跳变照样听得出来，这是 c2_0291 被判「噪声忽有忽无」的原因

用法：
  G:/Python310/python.exe _dn_uniform.py --in _audio_ch123/out_deliver \
      --out _dn_try --ids c2_0291,c2_0299 --probe
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def stft(y, n, hop):
    win = np.hanning(n)
    pad = n
    yp = np.concatenate([np.zeros(pad), y, np.zeros(pad)])
    cnt = 1 + (len(yp) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(cnt)[:, None]
    return np.fft.rfft(yp[idx] * win, axis=1), win, pad, cnt


def istft(Y, n, hop, pad, cnt, length):
    win = np.hanning(n)
    frames = np.fft.irfft(Y, n=n, axis=1) * win
    out = np.zeros((cnt - 1) * hop + n)
    wsum = np.zeros_like(out)
    for i in range(cnt):
        s = i * hop
        out[s:s + n] += frames[i]
        wsum[s:s + n] += win ** 2
    out = out / np.maximum(wsum, 1e-9)
    return out[pad:pad + length]


def denoise(y, sr, over=1.6, gmin_db=-20.0, pct=15.0, smooth=0.6,
            floor_db=-72.0, gate_rel_db=45.0, gate_extra_db=14.0):
    n = 2048 if sr > 24000 else 1024
    hop = n // 4
    Y, win, pad, cnt = stft(y, n, hop)
    mag = np.abs(Y)
    # 1. 稳态噪声谱：逐频点低分位
    N = np.percentile(mag, pct, axis=0)
    N = np.maximum(N, 1e-10)
    # 频域 3 点平滑，压音乐噪声
    ker = np.array([0.25, 0.5, 0.25])
    N = np.convolve(np.pad(N, 1, mode="edge"), ker, mode="valid")
    # 2. Wiener 谱减
    snr = (mag ** 2) / (N[None, :] ** 2 + 1e-18)
    g = np.maximum(10 ** (gmin_db / 20.0), 1.0 - over / np.maximum(np.sqrt(snr), 1e-6))
    # 时间平滑（一阶 IIR），减少音乐噪声与抽气感
    gs = np.empty_like(g)
    acc = g[0]
    for i in range(len(g)):
        acc = smooth * acc + (1 - smooth) * g[i]
        gs[i] = acc
    z = istft(Y * gs, n, hop, pad, cnt, len(y))

    # 3. 残留底噪统一
    z = unify_floor(z, sr, floor_db, gate_rel_db, gate_extra_db)
    return z.astype(np.float32), dict(
        noise_pct=pct, denoise_gain_db=float(np.mean(20 * np.log10(np.maximum(gs.mean(1), 1e-9)))))


def frame_db(y, sr, hop=0.01, win=0.03):
    h, w = int(hop * sr), int(win * sr)
    w = min(w, len(y))
    cnt = 1 + max(0, (len(y) - w) // h)
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(cnt)[:, None], 0, len(y) - 1)
    e = np.sqrt((y[idx] ** 2).mean(1)) + 1e-12
    return 20 * np.log10(e), h, w


def unify_floor(y, sr, floor_db, rel_db, extra_db, smooth_ms=25.0):
    """把「明显低于语音」的帧压到 floor_db；语音帧保持 1.0。

    阈值 = p97 − rel_db；再额外降 extra_db 保证测得底噪落到 floor 附近。
    """
    db, h, w = frame_db(y, sr)
    p97 = float(np.percentile(db, 97))
    thr = p97 - rel_db
    # 目标增益：让这些帧的电平到 floor_db
    tgt = 10 ** ((floor_db - db) / 20.0)
    g = np.where(db < thr, np.minimum(1.0, tgt), 1.0)
    # 平滑，避免硬切
    k = max(1, int(round(smooth_ms / 1000.0 / 0.01)))
    if len(g) > 2 * k:
        pad = np.pad(g, k, mode="edge")
        g = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1), axis=1)
    ker = np.hanning(max(3, 2 * k + 1)); ker /= ker.sum()
    g = np.convolve(np.pad(g, len(ker) // 2, mode="edge"), ker, mode="valid")[: len(g)]
    centers = np.arange(len(g)) * h + w / 2
    gi = np.interp(np.arange(len(y)), centers, g)
    return y * gi


def floor_db_of(y, sr):
    db, _, _ = frame_db(y, sr)
    return float(np.percentile(db, 10.0)), float(np.percentile(db, 97)), float(np.percentile(db, 5))


def snr_of(y, sr):
    db, _, _ = frame_db(y, sr)
    return float(np.percentile(db, 95) - np.percentile(db, 10))


def fill_floor(y, sr, floor_db=-72.0, rel_db=45.0, smooth_ms=50.0, seed=0):
    """把「非语音段」统一替换成 floor_db 的平稳底噪。

    为什么需要：插停顿 / 裁假尾时往间隙灌的是**数字零**（−inf），
    而语音段自带 −50~−70 dBFS 环境噪。两者差 50 dB 以上，耳朵听到的就是
    「嘶——/死寂/嘶——」，也就是用户说的「前面逗号和后面都有噪声」。
    实测全库 out/ 有 276 条带 >=10ms 零段，c2_0291 最狠：55 段、1282ms、占 28.5%。

    做法：低能帧先压到极低（去掉原来的不规则噪声），再叠一层恒定电平白噪。
    语音帧 g=0，完全不动 ⇒ 不吃字、不改音色。
    """
    db, h, w = frame_db(y, sr)
    p97 = float(np.percentile(db, 97))
    thr = p97 - rel_db
    g = (db < thr).astype(np.float64)
    k = max(1, int(round(smooth_ms / 1000.0 / 0.01)))
    if len(g) > 2 * k:
        pad = np.pad(g, k, mode="edge")
        g = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1), axis=1)
    ker = np.hanning(max(3, 2 * k + 1)); ker /= ker.sum()
    g = np.convolve(np.pad(g, len(ker) // 2, mode="edge"), ker, mode="valid")[: len(g)]
    centers = np.arange(len(g)) * h + w / 2
    gi = np.clip(np.interp(np.arange(len(y)), centers, g), 0.0, 1.0)

    # 绝对静音（数字零 / 死寂）必须 100% 填 —— 平滑核只有 50ms，
    # 11~33ms 的短零段会被拉到 gi≈0.5，残留成「极轻的洞」，所以这里强制拉满
    hard = (db < max(thr - 15.0, -90.0)).astype(np.float64)
    if hard.any():
        hk = max(1, int(round(0.008 / 0.01)))          # 8ms 外扩，盖住零段边缘
        if len(hard) > 2 * hk:
            hp = np.pad(hard, hk, mode="edge")
            hard = np.max(np.lib.stride_tricks.sliding_window_view(hp, 2 * hk + 1), axis=1)
        hi = np.interp(np.arange(len(y)), centers, hard)
        gi = np.maximum(gi, np.clip(hi, 0.0, 1.0))

    rng = np.random.default_rng(seed)
    nz = rng.standard_normal(len(y))
    nz = nz / (np.sqrt((nz ** 2).mean()) + 1e-12) * (10 ** (floor_db / 20.0))

    # 低能段：先压掉原噪声（×0.02 = −34dB），再叠加恒定底噪
    return (y * (1.0 - gi) + y * 0.02 * gi + nz * gi).astype(np.float32)


def norm_rms(y, sr, target_db=-24.0):
    """按 voiced 帧（> p70）的 RMS 归一到 target。"""
    db, h, w = frame_db(y, sr)
    m = db > np.percentile(db, 70)
    cnt = 1 + max(0, (len(y) - w) // h)
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(cnt)[:, None], 0, len(y) - 1)
    seg = y[idx][m]
    r = np.sqrt((seg ** 2).mean()) + 1e-12
    cur = 20 * np.log10(r)
    return y * (10 ** ((target_db - cur) / 20.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--over", type=float, default=1.6)
    ap.add_argument("--gmin", type=float, default=-20.0)
    ap.add_argument("--pct", type=float, default=15.0)
    ap.add_argument("--floor", type=float, default=-72.0)
    ap.add_argument("--rel", type=float, default=45.0)
    ap.add_argument("--extra", type=float, default=14.0)
    ap.add_argument("--norm", type=float, default=-24.0, help="voiced RMS 目标 dBFS，0 = 不归一")
    ap.add_argument("--mode", default="both", choices=["both", "fill", "sub"],
                    help="both=谱减+填底噪；fill=只统一底噪（不动语音，最安全）；sub=只谱减")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", default="G:/_setup/_dn_uniform_report.json")
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = ([os.path.join(a.inp, i + ".wav") for i in ids] if ids
             else sorted(glob.glob(os.path.join(a.inp, "*.wav"))))
    if not a.probe:
        os.makedirs(a.out, exist_ok=True)

    rep = {}
    for f in files:
        if not os.path.exists(f):
            print("缺", f)
            continue
        y, sr = sf.read(f, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        f0, p97_0, p5_0 = floor_db_of(y, sr)
        s0 = snr_of(y, sr)
        if a.mode == "fill":
            z = fill_floor(y, sr, floor_db=a.floor, rel_db=a.rel)
            info = {}
        elif a.mode == "sub":
            z, info = denoise(y, sr, a.over, a.gmin, a.pct, floor_db=a.floor,
                              gate_rel_db=a.rel, gate_extra_db=a.extra)
        else:
            z, info = denoise(y, sr, a.over, a.gmin, a.pct, floor_db=a.floor,
                              gate_rel_db=a.rel, gate_extra_db=a.extra)
            z = fill_floor(z, sr, floor_db=a.floor, rel_db=a.rel)
        if a.norm:
            z = norm_rms(z, sr, a.norm)
            pk = float(np.abs(z).max())
            if pk > 0.97:
                z = z * (0.97 / pk)
        f1, p97_1, p5_1 = floor_db_of(z, sr)
        s1 = snr_of(z, sr)
        tag = os.path.basename(f)[:-4]
        rep[tag] = dict(floor_before=round(f0, 1), floor_after=round(f1, 1),
                        snr_before=round(s0, 1), snr_after=round(s1, 1),
                        peak=round(float(np.abs(z).max()), 3),
                        peak_before=round(float(np.abs(y).max()), 3),
                        dur=round(len(y) / sr, 2))
        print("%-10s 底噪 %6.1f → %6.1f dB    SNR %5.1f → %5.1f dB    峰值 %.2f→%.2f %s"
              % (tag, f0, f1, s0, s1, rep[tag]["peak_before"], rep[tag]["peak"],
                 "" if a.probe else "写"))
        if not a.probe:
            sf.write(os.path.join(a.out, os.path.basename(f)), z, sr, subtype="PCM_24")
    if a.report and not a.probe:
        old = json.load(open(a.report, encoding="utf-8")) if os.path.exists(a.report) else {}
        old.update(rep)
        json.dump(old, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("-> " + a.report)
    print("处理 %d 条" % len(rep))


if __name__ == "__main__":
    main()
