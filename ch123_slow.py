# -*- coding: utf-8 -*-
"""统一语速：rubberband 保音高降速（只降不升），按角色分配目标。

- Charles（内敛、克制）目标 175 wpm
- Hooper（强势、外放）  目标 195 wpm
- tempo = 目标 / 当前有声语速，夹在 [0.72, 1.0]；低于目标的不提速（提速会让音色发紧）
- 降速后重新过一遍电平规范（-24dBFS voiced + 限峰）

用法：python ch123_slow.py [--src ch123] [--dst ch123_rate] [--dry]
"""
import glob
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_unify as U
from ch123_plan import INNER, PLAN

FF = "E:/tool/oopz/ffmpeg.exe"
TMP = "G:/_setup/_rate_tmp"

TARGET = {"C": 205.0, "E": 215.0}
TEMPO_MIN = 0.72

WORDS = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
WORDS.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
WHO.update({"I%02d" % i: w for i, (_, w, _, _) in enumerate(INNER)})


def stretch(src, dst, tempo):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality:transients=crisp" % tempo,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def voiced_rate(a, sr, n):
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return n / v * 60 if v > 0 else 0.0


def main():
    args = sys.argv[1:]
    src, dst = "G:/_setup/ch123", "G:/_setup/ch123_rate"
    dry = "--dry" in args
    for i, x in enumerate(args):
        if x == "--src":
            src = args[i + 1]
        if x == "--dst":
            dst = args[i + 1]
    os.makedirs(dst, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)

    rows = []
    for f in sorted(glob.glob(os.path.join(src, "*.wav"))):
        k = os.path.basename(f)[:-4]
        if k not in WORDS:
            continue
        who = WHO.get(k, "C")
        tgt = TARGET[who]
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        n = WORDS[k]
        r0 = voiced_rate(a, sr, n)
        tempo = 1.0
        if r0 > tgt * 1.02:
            tempo = max(TEMPO_MIN, tgt / r0)
        out = os.path.join(dst, k + ".wav")
        if dry:
            rows.append((k, who, n, r0, tempo, 0, 0))
            continue
        if tempo < 0.999:
            tmp = os.path.join(TMP, k + "_r.wav")
            sf.write(tmp, a, sr, subtype="PCM_16")
            stretch(tmp, tmp + ".wav", tempo)
            b, sr2 = sf.read(tmp + ".wav", dtype="float32", always_2d=True)
            b = b.mean(1)
        else:
            b = a
        y = U.proc(b, sr)
        sf.write(out, y, sr, subtype="PCM_16")
        r1 = voiced_rate(y, sr, n)
        rows.append((k, who, n, r0, tempo, r1, len(y) / sr))
        print("%-5s %s  %5.0f → %5.0f wpm  tempo %.3f  %5.2fs" %
              (k, who, r0, r1, tempo, len(y) / sr), flush=True)

    for who in ("C", "E"):
        sub = [r for r in rows if r[1] == who]
        if not sub:
            continue
        b4 = [r[3] for r in sub]
        af = [r[5] if not dry else r[3] for r in sub]
        print("\n== %s 目标 %.0f ==" % (who, TARGET[who]))
        print("  改前 %.0f-%.0f wpm（跨度 %.0f）" % (min(b4), max(b4), max(b4) - min(b4)))
        if not dry:
            print("  改后 %.0f-%.0f wpm（跨度 %.0f）" % (min(af), max(af), max(af) - min(af)))
        print("  tempo 中位 %.3f，最低 %.3f" % (float(np.median([r[4] for r in sub])),
                                                min(r[4] for r in sub)))


if __name__ == "__main__":
    main()
