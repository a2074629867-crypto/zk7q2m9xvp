# -*- coding: utf-8 -*-
"""c2_0191 覆盖率控制实验：把「静音」和「fmin 贴边」两个干扰排除掉。

上一版测出 old 覆盖率 16.9% / new 35.1%，但那个分母是「总帧数」，含静音。
本脚本：
  1. 能量门限先定「有声帧」（20ms 帧，阈值 = p90 − 20dB，与 _speedlib 同源）
  2. 只在有声帧里算 F0 可跟踪率
  3. fmin 取 50 / 60 / 75 三档，看结论是否随参数翻转（敏感性检查）
"""
import os

import librosa
import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SID = "c2_0191"
SR16 = 16000
HOP = 160
FL = 0.02


def load(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return librosa.resample(y, orig_sr=sr, target_sr=SR16), len(y) / float(sr)


def frame_db(y):
    n = int(FL * SR16)
    h = HOP
    k = 1 + (len(y) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    return 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12)


def voiced_mask(y):
    db = frame_db(y)
    thr = max(-60.0, float(np.percentile(db, 90)) - 20.0)
    return db > thr, thr


def f0_mask(y, fmin):
    f0, vflag, _ = librosa.pyin(y, fmin=fmin, fmax=400, sr=SR16,
                                frame_length=1024, hop_length=HOP)
    return vflag & np.isfinite(f0)


def main():
    print("=== c2_0191 覆盖率控制（分母 = 有声帧）===")
    print("%-5s %-5s %8s %8s %8s %8s %8s"
          % ("版", "fmin", "有声帧", "有F0", "覆盖率", "阈值dB", "F0中位"))
    store = {}
    for tag, sub in (("old", "_audio_ch123/out"), ("new", "_regen_final")):
        p = os.path.join(ROOT, sub, SID + ".wav")
        if not os.path.exists(p):
            print("缺", p)
            continue
        y, dur = load(p)
        vm0, thr = voiced_mask(y)
        for fmin in (50, 60, 75):
            f0, vflag, _ = librosa.pyin(y, fmin=fmin, fmax=400, sr=SR16,
                                        frame_length=1024, hop_length=HOP)
            ok = vflag & np.isfinite(f0)
            n = min(len(vm0), len(ok))
            vm, ok = vm0[:n], ok[:n]
            m = int((vm & ok).sum())
            cov = m / max(1, int(vm.sum()))
            med = float(np.median(f0[:n][ok & vm])) if (ok & vm).sum() else float("nan")
            print("%-5s %-5d %8d %8d %8.3f %8.1f %8.1f"
                  % (tag, fmin, int(vm.sum()), m, cov, thr, med))
            store[(tag, fmin)] = cov

    print()
    print("=== 敏感性检查：换 fmin 结论会不会翻转 ===")
    for fmin in (50, 60, 75):
        a = store.get(("old", fmin))
        b = store.get(("new", fmin))
        if a is None or b is None:
            continue
        print("  fmin=%-3d  old %.3f  new %.3f  差 %+.3f  →  %s 高"
              % (fmin, a, b, b - a, "new" if b > a else "old"))


if __name__ == "__main__":
    main()
