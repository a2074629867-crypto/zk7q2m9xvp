# -*- coding: utf-8 -*-
"""统一语速 v2：只拉伸"有声段"，停顿保持原样。

v1 的坑：rubberband 作用在整段上，静音也被同比拉长 ⇒ L050 从 2.72s 变 5.24s，
语速是对了，但中间那些停顿拖成两倍，整体听着发飘。

v2 流程：
  1) 按静音切段（min_gap 0.12，切点一定落在词间静音里，不会切到音）
  2) 每段单独 rubberband 保音高变速（tempo = 目标/当前有声语速，夹 [0.66, 1.0]）
  3) 按原 gap 时长重新拼，段首尾各 8ms 淡入淡出防咔哒
  4) 过电平规范（-24dBFS + 限峰）

用法：python ch123_slow2.py [--dst ch123_rate] [--only L050,L084]
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
TMP = "G:/_setup/_rate_tmp2"

TARGET = {"C": 175.0, "E": 195.0}
TEMPO_MIN = 0.66
FADE = 0.008

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


def process(a, sr, n, target):
    segs = RB.split_at_silence(a, sr, min_gap=0.12)
    if len(segs) < 1:
        return a, 1.0, 0.0
    voiced = sum(b - c for c, b in segs)
    rate = n / voiced * 60 if voiced else 0.0
    tempo = 1.0
    if rate > target * 1.02:
        tempo = max(TEMPO_MIN, target / rate)

    if tempo >= 0.999:
        return a, 1.0, rate

    pieces = []
    prev = 0.0
    stretched_len = 0.0
    for i, (s0, s1) in enumerate(segs):
        # 保留段前静音（原样）
        if s0 > prev:
            pieces.append(a[int(prev * sr):int(s0 * sr)])
        seg = a[int(s0 * sr):int(s1 * sr)].copy()
        seg = fade(seg, sr)
        sp = os.path.join(TMP, "s%03d.wav" % i)
        sf.write(sp, seg, sr, subtype="PCM_16")
        stretch_file(sp, sp + ".wav", tempo)
        b, _ = sf.read(sp + ".wav", dtype="float32", always_2d=True)
        b = b.mean(1)
        fade(b, sr)
        pieces.append(b)
        stretched_len += len(b) / sr
        prev = s1
    if prev < len(a) / sr:
        pieces.append(a[int(prev * sr):])

    y = np.concatenate(pieces).astype(np.float32)
    r2 = n / max(stretched_len, 1e-6) * 60
    return y, tempo, r2


def main():
    args = sys.argv[1:]
    dst = "G:/_setup/ch123_rate"
    only = None
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
        segs = RB.split_at_silence(a, sr, min_gap=0.12)
        v = sum(b - c for c, b in segs)
        r0 = n / v * 60 if v else 0.0
        y, tempo, r1 = process(a, sr, n, tgt)
        y = U.proc(y, sr)
        sf.write(os.path.join(dst, k + ".wav"), y, sr, subtype="PCM_16")
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
        print("  改前 %.0f-%.0f（跨度 %.0f）→ 改后 %.0f-%.0f（跨度 %.0f）" %
              (min(b4), max(b4), max(b4) - min(b4), min(af), max(af), max(af) - min(af)))


if __name__ == "__main__":
    main()
