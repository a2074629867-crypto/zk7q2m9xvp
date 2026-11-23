# -*- coding: utf-8 -*-
"""语速统一 v4：按"发音时长"（去掉间隔）算速率，双向拉平。

刻度：把每条按静音切成语音段，只累加语音段时长 ⇒ voiced wpm
      （间隔不计入，这正是"同语气同语调"该对齐的量）
做法：每段单独 rubberband 保音高变速（不改音高、不改共振峰），
      段间静音按原样保留 —— 间隔长度不动，只改发音本身
上下限：0.66（再往下辅音会糊，ASR 已实测崩）/ 1.30
目标：Charles 205 / Hooper 220（性格不同，各自内部统一）

用法：python ch123_slow4.py [--dst ch123_rate] [--only L050,L084] [--dry]
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
TMP = "G:/_setup/_rate_tmp4"

TARGET = {"C": 205.0, "E": 220.0}
TEMPO_MIN, TEMPO_MAX = 0.66, 1.30
# 拉伸后辅音必糊的条目：保持原速（已实测 0.70-0.78 全档位 ASR 都不对）
EXEMPT = {"L084": 1.0}
FADE = 0.006

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


def rate_of(a, sr, n):
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return (n / v * 60 if v > 0 else 0.0), v


def stretch_file(src, dst, tempo):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality:transients=crisp" % tempo,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def stretch_segments(a, sr, tempo, tag):
    """只变速语音段，段间静音原样保留。"""
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
        tempo = 1.0
        if k in EXEMPT:
            tempo = EXEMPT[k]
        elif r0 > 0:
            tempo = min(TEMPO_MAX, max(TEMPO_MIN, tgt / r0))
        if dry:
            print("%-5s %s %5.0f → tempo %.3f → %5.0f" % (k, who, r0, tempo, r0 * tempo))
            continue

        y = stretch_segments(a, sr, tempo, k) if abs(tempo - 1.0) > 0.005 else a
        y = U.proc(y, sr)
        sf.write(os.path.join(dst, k + ".wav"), y, sr, subtype="PCM_16")
        r1, _ = rate_of(y, sr, n)
        rows.append((k, who, r0, r1, tempo, len(y) / sr))
        print("%-5s %s  %5.0f → %5.0f wpm  tempo %.3f  %5.2fs" %
              (k, who, r0, r1, tempo, len(y) / sr), flush=True)

    for who in ("C", "E"):
        sub = [r for r in rows if r[1] == who]
        if not sub:
            continue
        b4 = [r[2] for r in sub]
        af = [r[3] for r in sub]
        print("\n== %s 目标 %.0f ==" % (who, TARGET[who]))
        print("  %.0f-%.0f（跨度 %.0f）→ %.0f-%.0f（跨度 %.0f）" %
              (min(b4), max(b4), max(b4) - min(b4), min(af), max(af), max(af) - min(af)))


if __name__ == "__main__":
    main()
