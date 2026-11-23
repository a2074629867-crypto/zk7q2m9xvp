# -*- coding: utf-8 -*-
"""给句尾加升调（疑问语气），PSOLA 重合成，不改音色。

    G:/Python310/python.exe ch123_qbend.py in.wav out.wav [rise=3.0] [tail=0.30]

做法：
  1. 取最后一个有声帧往回 tail 秒作为「升调区」
  2. 在该区做线性 pitch 抬升（0 → rise 半音），越过终点后再 60ms 落回
  3. 用 Praat Manipulation（PSOLA）重合成，保持时长/共振峰
"""
import sys

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call


def read_wav(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1).astype(np.float64), sr


def voiced_end(a, sr, thr_db=-45.0, win=0.01):
    n = int(win * sr)
    k = len(a) // n
    if k < 2:
        return len(a) / sr
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    idx = np.where(db > thr_db)[0]
    return (idx[-1] + 1) * win if len(idx) else len(a) / sr


def bend(a, sr, rise=3.0, tail=0.30, fade=0.06, fmin=60, fmax=500):
    dur = len(a) / sr
    end = voiced_end(a, sr)
    t0 = max(0.0, end - tail)
    t1 = min(dur, end + fade)
    snd = parselmouth.Sound(a, sampling_frequency=sr)
    man = call(snd, "To Manipulation", 0.01, fmin, fmax)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    tier = call(pitch, "To PitchTier")
    n = int(call(tier, "Get number of points"))
    if n < 2:
        return a
    ts = [float(call(tier, "Get time from index", i)) for i in range(1, n + 1)]
    fs = [float(call(tier, "Get value at index", i)) for i in range(1, n + 1)]

    pts = []
    for t, f in zip(ts, fs):
        if f <= 0:
            continue
        if t < t0:
            k = 0.0
        elif t <= end:
            k = (t - t0) / max(1e-6, end - t0)
        else:
            k = max(0.0, 1.0 - (t - end) / max(1e-6, t1 - end))
        pts.append((t, f * 2 ** (rise * k / 12.0)))

    # 倒序删除原有点，再写入新点（正序添加在 Praat 里会自动排序）
    for i in range(n, 0, -1):
        call(tier, "Remove point", i)
    for t, f in pts:
        call(tier, "Add point", t, f)

    call(man, "Replace pitch tier", tier)
    out = call(man, "Get resynthesis (overlap-add)")
    return np.array(out.values).ravel()


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rise = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    tail = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
    a, sr = read_wav(src)
    y = np.clip(bend(a, sr, rise, tail), -1, 1)
    sf.write(dst, y.astype(np.float32), sr)
    print("%s -> %s  rise=%+.1f st tail=%.2fs  %.2fs" % (src, dst, rise, tail, len(y) / sr))


if __name__ == "__main__":
    main()
