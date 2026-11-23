# -*- coding: utf-8 -*-
"""_denoise_floor.py —— 去底噪（为「插停顿」做准备）

用户 2026-11-21 的要求：
  「人工停顿没错，问题是要听不出来；可以把生成完的语音去掉底噪再加入停顿，
    就不会很明显了」

原理：听得出「假停顿」不是因为有停顿，而是因为**底噪电平不连续** ——
原音频静音处有 −50~−58 dBFS 的嘶声，注入的数字零是 −inf，落差 50 dB 以上，
耳朵听到的是「嘶——/死寂/嘶——」。把底噪先压到听不见（≤ −75 dBFS），
再注入数字零，落差就落在听觉门限以下，也就听不出来。

两种模式：
  gate  只压「非语音帧」的增益（向下扩展），不碰频谱 ⇒ 不动音色，
        过七闸的声纹/tilt 几乎不变。默认。
  nr    noisereduce 平稳谱减（会把气声一起削掉，慎用）

用法：
  G:/Python310/python.exe _denoise_floor.py --in _audio_ch123/out \
      --out _audio_ch123/out_dn --ids c2_0246,c2_0299
  G:/Python310/python.exe _denoise_floor.py --in ... --out ... --probe   # 只报指标
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf


def frame_db(y, sr, hop=0.01, win=0.025):
    h = int(hop * sr)
    w = int(win * sr)
    n = 1 + max(0, (len(y) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    e = np.sqrt((y[idx] ** 2).mean(1)) + 1e-12
    return 20 * np.log10(e), h, w


def gate(y, sr, atten_db=30.0, rel_db=40.0, smooth_ms=40.0):
    """非语音帧整体降 atten_db；语音帧不动。

    阈值取「帧能量的高点 −rel_db」：rel_db 太小会把气声也关掉（气声只比峰值低 20~30 dB），
    40 dB 只关真正的底噪。
    """
    db, h, w = frame_db(y, sr)
    peak = float(np.percentile(db, 99.0))
    thr = peak - rel_db
    g = np.where(db > thr, 1.0, 10 ** (-atten_db / 20.0)).astype(np.float64)
    # 平滑增益包络：先做中值去掉孤立跳变，再用 hann 卷积软化起落（避免咔哒/抽气声）
    k = max(1, int(round(smooth_ms / 1000.0 / 0.01)))
    if len(g) > k + 2:
        pad = np.pad(g, k, mode="edge")
        g = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1), axis=1)
    ker = np.hanning(max(3, k * 2 + 1))
    ker /= ker.sum()
    g = np.convolve(np.pad(g, len(ker) // 2, mode="edge"), ker, mode="valid")[: len(g)]
    # 帧中心 → 采样点，线性插值
    centers = np.arange(len(g)) * h + w / 2
    gi = np.interp(np.arange(len(y)), centers, g)
    return (y * gi).astype(np.float32)


def nr(y, sr, prop=1.0):
    import noisereduce as NR
    return NR.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=prop).astype(np.float32)


def floor_db(y, sr):
    db, _, _ = frame_db(y, sr)
    return float(np.percentile(db, 10.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--mode", default="gate", choices=["gate", "nr"])
    ap.add_argument("--atten", type=float, default=30.0)
    ap.add_argument("--rel", type=float, default=40.0)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", default="G:/_setup/_denoise_report.json")
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
        f0 = floor_db(y, sr)
        z = gate(y, sr, a.atten, a.rel) if a.mode == "gate" else nr(y, sr)
        f1 = floor_db(z, sr)
        sp0 = float(np.abs(y).max())
        sp1 = float(np.abs(z).max())
        tag = os.path.basename(f)[:-4]
        rep[tag] = dict(floor_before=round(f0, 1), floor_after=round(f1, 1),
                        peak_before=round(sp0, 3), peak_after=round(sp1, 3),
                        dur=round(len(y) / sr, 2))
        print("%-9s 底噪 %.0f → %.0f dBFS   峰值 %.2f → %.2f" % (tag, f0, f1, sp0, sp1))
        if not a.probe:
            sf.write(os.path.join(a.out, os.path.basename(f)), z, sr, subtype="PCM_16")
    if a.report:
        old = json.load(open(a.report, encoding="utf-8")) if os.path.exists(a.report) else {}
        old.update(rep)
        json.dump(old, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("处理 %d 条" % len(rep))


if __name__ == "__main__":
    main()
