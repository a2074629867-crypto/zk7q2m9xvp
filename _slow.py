# -*- coding: utf-8 -*-
"""WSOLA 变速：只拉长，不改音高，尽量保住爆破音与齿音。

为什么自己写：本机没有 ffmpeg、没有 rubberband、没有 pyrubberband；
librosa 只有相位声码器（对语音的塞音/气口会糊）。WSOLA 是在波形域做重叠相加 +
相似度搜索，40ms 帧 / 20ms 合成跳，语音上比 PV 干净。

用法：
  python _slow.py --wav in.wav --rate 0.85 --out out.wav     # rate<1 = 变慢
  python _slow.py --dir a --out b --target-wpm 190 --list ids.txt
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def wsola(y, sr, rate, frame_ms=40.0, synth_hop_ms=20.0, tol_ms=12.0):
    """rate<1 变慢（时长 = 原长 / rate）。返回同采样率的新波形。"""
    if abs(rate - 1.0) < 1e-3:
        return y.copy()
    stretch = 1.0 / rate                       # 时长放大倍数
    n = len(y)
    frame = int(frame_ms * 1e-3 * sr)
    frame += frame % 2
    Hs = int(synth_hop_ms * 1e-3 * sr)         # 合成跳（固定）
    Ha = Hs / stretch                          # 分析跳（浮点）
    tol = int(tol_ms * 1e-3 * sr)
    win = np.hanning(frame).astype(np.float32)

    n_out = int(np.ceil(n * stretch)) + frame
    out = np.zeros(n_out, dtype=np.float64)
    wsum = np.zeros(n_out, dtype=np.float64)

    k = 0
    prev_end = None                            # 上一帧在**输入**上的自然延续位置
    while True:
        centre = int(round(k * Ha))
        if centre + frame >= n:
            break
        if prev_end is None:
            pos = centre
        else:
            lo = max(0, centre - tol)
            hi = min(n - frame, centre + tol)
            best, pos = -1e18, centre
            tpl = y[prev_end:prev_end + frame]
            if len(tpl) == frame and hi > lo:
                seg = y[lo:hi + frame]
                # 归一化互相关（FFT 加速）
                c = np.correlate(seg, tpl, mode="valid")
                e = np.sqrt(np.convolve(seg ** 2, np.ones(frame), mode="valid")) + 1e-9
                score = c / e
                j = int(np.argmax(score))
                if score[j] > best:
                    pos = lo + j
            else:
                pos = max(0, min(n - frame, centre))
        o0 = k * Hs
        out[o0:o0 + frame] += y[pos:pos + frame] * win
        wsum[o0:o0 + frame] += win
        prev_end = pos + Hs                    # 自然延续：跳过合成跳那么多
        k += 1

    out = out[:int(np.ceil(n * stretch))]
    wsum = wsum[:len(out)]
    m = wsum > 1e-6
    out[m] /= wsum[m]
    # 结尾不足一帧的部分直接接原音最后一段，避免突然截断
    if len(out) < int(n * stretch):
        pad = int(n * stretch) - len(out)
        out = np.concatenate([out, y[-pad:] * 0.0])
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--rate", type=float, default=0.85)
    ap.add_argument("--out")
    ap.add_argument("--list")
    ap.add_argument("--dir")
    ap.add_argument("--target-wpm", type=float, default=190.0)
    ap.add_argument("--min-rate", type=float, default=0.78, help="最多拉慢到多少（保护音质）")
    a = ap.parse_args()

    import _rate as R

    if a.wav:
        y, sr = sf.read(a.wav, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        z = wsola(y, sr, a.rate)
        sf.write(a.out or (os.path.splitext(a.wav)[0] + "_slow.wav"), z, sr, subtype="PCM_16")
        print("%s %.2fs → %.2fs (rate %.2f)" % (os.path.basename(a.wav), len(y) / sr,
                                                len(z) / sr, a.rate))
        return

    plan = {}
    with open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                plan[d["id"]] = d

    ids = [x.strip() for x in open(os.path.join(HERE, a.list)).read().replace("\n", ",").split(",") if x.strip()]
    os.makedirs(a.out, exist_ok=True)
    print("%-9s %6s %6s %6s %6s %s" % ("id", "原wpm", "目标", "rate", "新wpm", "时长"))
    for rid in ids:
        p = os.path.join(HERE, "_audio_ch123/out/%s.wav" % rid)
        if not os.path.exists(p):
            continue
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        r = R.rate(p, plan[rid]["text"])
        cur = r["wpm_span"] or r["wpm"]
        rate = max(a.min_rate, min(1.0, a.target_wpm / cur)) if cur else 1.0
        z = wsola(y, sr, rate)
        op = os.path.join(a.out, "%s.wav" % rid)
        sf.write(op, z, sr, subtype="PCM_16")
        nr = R.rate(op, plan[rid]["text"])
        print("%-9s %6.0f %6.0f %6.3f %6.0f %.2f→%.2fs" % (
            rid, cur, a.target_wpm, rate, nr["wpm_span"] or 0, len(y) / sr, len(z) / sr))


if __name__ == "__main__":
    main()
