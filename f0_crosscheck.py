# -*- coding: utf-8 -*-
"""F0 突跳真伪复核：用独立估计器（librosa.pyin）重跑同一判据。

判据（与 narr_check 一致）：相邻 10ms 帧的 voiced F0 差 > F0_JUMP_ST 个半音，
且跳过去后 60ms 内仍维持在新音高（±2st）。

如果 parselmouth 说「有 2~6 次突跳」而 pyin 说「0 次」，那就是跟踪错误，不是语调。
pyin 用的是 YIN + 概率门限，与 praat 的自相关+倍频代价完全不同的机制，适合做独立复核。
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")

JUMP_ST = 9.0
HOLD = 0.06
HOLD_TOL = 2.0


def count_jumps(t, f, v, dt=0.03):
    """返回 (跳变次数, 最大跳幅)，要求跳后 60ms 内仍停在新音高。"""
    n, mx = 0, 0.0
    last = -9.0
    for i in range(1, len(t)):
        if not (v[i] and v[i - 1]):
            continue
        if t[i] - t[i - 1] > dt:
            continue
        d = abs(12 * np.log2(f[i] / f[i - 1]))
        if d <= JUMP_ST:
            continue
        # 跳后是否停住
        j = i + 1
        held = []
        while j < len(t) and t[j] - t[i] <= HOLD:
            if v[j]:
                held.append(12 * np.log2(f[j] / f[i]))
            j += 1
        if len(held) < 2:
            continue
        if abs(float(np.median(held))) <= HOLD_TOL:
            if t[i] - last > 0.08:
                n += 1
            last = t[i]
            mx = max(mx, d)
    return n, mx


def praat_f0(y, sr):
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(y, sr)
    p = call(snd, "To Pitch", 0.01, 60, 250)
    t = np.asarray(p.xs())
    f = np.asarray(p.selected_array["frequency"])
    return t, f, f > 0


def pyin_f0(y, sr):
    import librosa
    f, vflag, vprob = librosa.pyin(y, fmin=60, fmax=250, sr=sr,
                                   frame_length=2048, hop_length=int(0.01 * sr))
    t = np.arange(len(f)) * 0.01
    v = np.isfinite(f) & (vprob > 0.3)
    f = np.nan_to_num(f)
    return t, f, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="G:/_setup/_f0_crosscheck.json")
    a = ap.parse_args()

    rows = json.load(open("G:/_setup/_narr_check4/_narr_check.json", encoding="utf-8"))

    def _f0ish(x):
        """why 是 list（如 ['F0 236Hz 超 2.2×中位', '八度跟踪 1 处']），不是字符串。

        ★ 2026-11-14 修：原版按字符串 startswith 判，永远不成立；
          又按 verdict=="FIX" 取样（这份账本里 FIX 有 130 条），样本条件两处都错。
        """
        w = x.get("why") or []
        if isinstance(w, str):
            w = [w]
        return any(str(s).startswith(("F0", "八度")) for s in w)

    target = [r for r in rows if r["verdict"] in ("WATCH", "FIX") and _f0ish(r)]
    fx = target if not a.n else target[: a.n]
    ok = [r for r in rows if r["verdict"] == "PASS"][:5]

    res = []
    print("目标集 %d 条（WATCH/FIX 且 why 含 F0/八度），本次跑 %d 条" % (len(target), len(fx)))
    print("%-9s | %-22s | %-22s" % ("id", "parselmouth", "pyin"))
    print("%-9s | %5s %6s %6s | %5s %6s %6s" % ("", "n", "maxst", "medF0", "n", "maxst", "medF0"))
    for r in fx + ok:
        p = os.path.join("G:/_setup/_audio_ch123/out", r["unit"] + ".wav")
        if not os.path.exists(p):
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        t1, f1, v1 = praat_f0(y, sr)
        n1, m1 = count_jumps(t1, f1, v1)
        t2, f2, v2 = pyin_f0(y, sr)
        n2, m2 = count_jumps(t2, f2, v2)
        med1 = float(np.median(f1[v1])) if v1.any() else 0
        med2 = float(np.median(f2[v2])) if v2.any() else 0
        res.append(dict(unit=r["unit"], verdict=r["verdict"],
                        praat_n=n1, praat_max=round(m1, 1), praat_med=round(med1, 1),
                        pyin_n=n2, pyin_max=round(m2, 1), pyin_med=round(med2, 1)))
        print("%-9s | %5d %6.1f %6.1f | %5d %6.1f %6.1f  %s"
              % (r["unit"], n1, m1, med1, n2, m2, med2, r["verdict"]))

    both = [x for x in res if x["verdict"] == "FIX"]
    agree = sum(1 for x in both if x["pyin_n"] >= 2)
    print()
    print("FIX 样本 %d 条：pyin 也判 ≥2 次突跳的 %d 条（%.0f%%）"
          % (len(both), agree, 100.0 * agree / max(1, len(both))))
    print("⇒ 低一致率 = parselmouth 的突跳是跟踪错误，判据需按估计器稳健性重定")
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", a.out)


if __name__ == "__main__":
    main()
