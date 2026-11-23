# -*- coding: utf-8 -*-
"""统一语速 v3：只拉伸有声段，两轮迭代逼近目标，口径统一实测。

v1 坑：整段 rubberband 把停顿也拉长 ⇒ L050 2.72s → 5.24s，语速对了但气息散了。
v2 坑：r0 与 r1 口径不一致（一个 min_gap 0.22、一个量拉伸后总长）⇒ 目标算不准。
v3：切段只拉伸语音、停顿原样拼回；处理后用同一把尺（min_gap 0.22）实测，
    不够就按实测比例再降一轮。

用法：python ch123_slow3.py [--dst ch123_rate] [--only L050,L084] [--dry]
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
TMP = "G:/_setup/_rate_tmp3"

TARGET = {"C": 205.0, "E": 215.0}
TEMPO_MIN_SHORT = 0.72   # <12 词：拉伸过大 ASR 会崩
TEMPO_MIN_LONG = 0.72    # >=12 词：长句容忍度更高
FADE = 0.008
ROUNDS = 3

WORDS = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
WORDS.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
WHO.update({"I%02d" % i: w for i, (_, w, _, _) in enumerate(INNER)})


def fade(x, sr, sec=FADE):
    n = max(2, int(sec * sr))
    if len(x) < 2 * n:
        n = max(1, len(x) // 2)
    x[:n] *= np.linspace(0, 1, n)
    x[-n:] *= np.linspace(1, 0, n)
    return x


def stretch_file(src, dst, tempo):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality:transients=crisp" % tempo,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def rate_of(a, sr, n):
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return (n / v * 60 if v > 0 else 0.0), v


def stretch_once(a, sr, tempo, tag):
    """切段 → 每段独立变速 → 按原 gap 拼回。"""
    segs = RB.split_at_silence(a, sr, min_gap=0.12)
    pieces, prev = [], 0.0
    for i, (s0, s1) in enumerate(segs):
        if s0 > prev:
            pieces.append(a[int(prev * sr):int(s0 * sr)])
        seg = fade(a[int(s0 * sr):int(s1 * sr)].copy(), sr)
        sp = os.path.join(TMP, "%s_%03d.wav" % (tag, i))
        sf.write(sp, seg, sr, subtype="PCM_16")
        stretch_file(sp, sp + ".wav", tempo)
        b, _ = sf.read(sp + ".wav", dtype="float32", always_2d=True)
        pieces.append(fade(b.mean(1), sr))
        prev = s1
    if prev < len(a) / sr:
        pieces.append(a[int(prev * sr):])
    return np.concatenate(pieces).astype(np.float32)


def main():
    args = sys.argv[1:]
    dst = "G:/_setup/ch123_rate"
    only = None
    dry = "--dry" in args
    for i, x in enumerate(args):
        if x == "--dst":
            dst = args[i + 1]
        if x == "--only":
            only = set(args[i + 1].split(","))
    os.makedirs(dst, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)

    rows = []
    for f in sorted(glob.glob("G:/_setup/ch123/*.wav")):
        k = os.path.basename(f)[:-4]
        if k not in WORDS or (only and k not in only):
            continue
        who = WHO.get(k, "C")
        tgt = TARGET[who]
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        n = WORDS[k]
        r0, _ = rate_of(a, sr, n)
        if dry:
            print("%-5s %s %5.0f wpm → tempo %.3f" % (k, who, r0, max(TEMPO_MIN_LONG if n >= 12 else TEMPO_MIN_SHORT, tgt / r0)))
            continue

        cur, r = a, r0
        total_tempo = 1.0
        tmin_total = TEMPO_MIN_LONG if n >= 12 else TEMPO_MIN_SHORT
        for rd in range(ROUNDS):
            if r <= tgt * 1.05:
                break
            t = max(0.85, tgt / r)                     # 单轮最多降 15%
            if total_tempo * t < tmin_total:           # 累积不得越过下限
                t = tmin_total / total_tempo
            if t > 0.995:
                break
            cur = stretch_once(cur, sr, t, "%s_r%d" % (k, rd))
            total_tempo *= t
            r, _ = rate_of(cur, sr, n)
        y = U.proc(cur, sr)
        sf.write(os.path.join(dst, k + ".wav"), y, sr, subtype="PCM_16")
        r1, _ = rate_of(y, sr, n)
        rows.append((k, who, r0, r1, total_tempo, len(y) / sr))
        print("%-5s %s  %5.0f → %5.0f wpm  tempo %.3f  %5.2fs" %
              (k, who, r0, r1, total_tempo, len(y) / sr), flush=True)

    for who in ("C", "E"):
        sub = [r for r in rows if r[1] == who]
        if not sub:
            continue
        b4 = [r[2] for r in sub]
        af = [r[3] for r in sub]
        print("\n== %s 目标 %.0f ==" % (who, TARGET[who]))
        print("  %.0f-%.0f（跨度 %.0f）→ %.0f-%.0f（跨度 %.0f）" %
              (min(b4), max(b4), max(b4) - min(b4), min(af), max(af), max(af) - min(af)))
        print("  tempo 中位 %.3f / 最低 %.3f" %
              (float(np.median([r[4] for r in sub])), min(r[4] for r in sub)))


if __name__ == "__main__":
    main()
