# -*- coding: utf-8 -*-
"""逐条体检：时长 / 语速 / 中位F0 / 句尾升调 / 有声占比。

    G:/Python310/python.exe ch123_probe.py [文件或目录 ...]

输出列：
    dur    总时长
    wpm    按总时长的语速
    vwpm   按有声段的语速（真实发音速度）
    F0     中位基频
    tail   句尾 250ms 相对句中位基频的半音差（>+1.5 = 升调，疑问感）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import parselmouth
import soundfile as sf


def read_wav(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def voiced_mask(a, sr, win=0.01, thr_db=-45.0):
    n = int(win * sr)
    k = len(a) // n
    if k < 2:
        return np.zeros(1, dtype=bool), win
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    return db > thr_db, win


def f0_track(a, sr, fmin=60, fmax=400):
    snd = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    return pitch.xs(), pitch.selected_array["frequency"]


def probe(p, words=None):
    a, sr = read_wav(p)
    dur = len(a) / sr
    vm, win = voiced_mask(a, sr)
    vdur = float(vm.sum()) * win
    t, f = f0_track(a, sr)
    good = f > 0
    med = float(np.median(f[good])) if good.any() else 0.0
    # 句尾：最后一个有声帧往前 250ms
    tail_st = None
    if good.any():
        last = float(t[good][-1])
        sel = good & (t >= last - 0.25)
        if sel.sum() >= 3:
            tmed = float(np.median(f[sel]))
            if med > 0 and tmed > 0:
                tail_st = 12.0 * np.log2(tmed / med)
    wpm = (words / dur * 60.0) if words else None
    vwpm = (words / vdur * 60.0) if (words and vdur > 0.2) else None
    return dict(dur=dur, vdur=vdur, vr=(vdur / dur if dur else 0), f0=med,
                tail=tail_st, wpm=wpm, vwpm=vwpm)


def main():
    targets = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            targets += [os.path.join(arg, f) for f in sorted(os.listdir(arg))
                        if f.lower().endswith(".wav")]
        elif os.path.exists(arg):
            targets.append(arg)
    try:
        from ch123_plan import PLAN, INNER
        wmap = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
        wmap.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})
    except Exception:
        wmap = {}

    print("%-8s %6s %6s %6s %6s %7s %7s %6s" %
          ("文件", "时长", "有声%", "wpm", "vwpm", "F0", "句尾半音", "词数"))
    for p in targets:
        name = os.path.basename(p)[:-4]
        w = wmap.get(name)
        r = probe(p, w)
        print("%-8s %6.2f %5.0f%% %6s %6s %7.1f %8s %6s" % (
            name, r["dur"], 100 * r["vr"],
            "%.0f" % r["wpm"] if r["wpm"] else "-",
            "%.0f" % r["vwpm"] if r["vwpm"] else "-",
            r["f0"], ("%+.1f" % r["tail"]) if r["tail"] is not None else "-",
            w or "-"))


if __name__ == "__main__":
    main()
