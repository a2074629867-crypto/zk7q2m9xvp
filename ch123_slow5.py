# -*- coding: utf-8 -*-
"""语速统一 v5：voiced wpm + 按句长分级目标。

用户口径（2026-10-19）：
  "超短句可以慢啊，长句快点很正常，短句快了就不到 1 秒了"
⇒ 目标不是全库一个数，而是**词数越少目标越慢**：
  短句留气口、留重音，长句自然流畅。
  同时按角色偏移：Charles 内敛 -6，Hooper 外放 +6。

做法：按静音切语音段 → 只对语音段做 rubberband 保音高变速 →
      段间静音原样拼回（停顿不动）。tempo 下限短句放宽到 0.62。
目标表见 TBL。
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
TMP = "G:/_setup/_rate_tmp5"

# 用户校准（20:52）：290wpm 拉到 204 是"慢过头"，In Wales 203 不该降
# ⇒ 不再按词数分级，统一收到 250 左右；原速本来就 ≤255 的直接不动
TBL = [
    (1, 999, 252),
]
BIAS = {"C": 0.0, "E": 6.0}

# 用户硬限制（20:51）：最慢只能到原音频的 0.7 倍，再低就"蹦"了
TEMPO_FLOOR = 0.70


def tempo_floor(n, dur):
    return TEMPO_FLOOR

# 用户口径（20:13）："原声慢的不用加快好不好" ⇒ 只降不升
TEMPO_MAX = 1.0
# L084：句尾 "I said" 本来就弱，0.70-0.78 全糊，只能重生成
# L058：1.28s 已过 1 秒线，拉伸后 "then" 被识别吞掉，保持原速
# L078：No.+But 是剪贴拼接，再变速会散
# L092：原声 130wpm 本来就慢，不碰
EXEMPT = {"L084": 1.0, "L058": 1.0, "L078": 1.0, "L092": 1.0}
FADE = 0.006

WORDS = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
WORDS.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})
WHO = {"L%03d" % i: w for i, w, _, _ in PLAN}
WHO.update({"I%02d" % i: w for i, (_, w, _, _) in enumerate(INNER)})


def target_of(n, who):
    for lo, hi, v in TBL:
        if lo <= n <= hi:
            return v + BIAS.get(who, 0.0)
    return 216.0 + BIAS.get(who, 0.0)


def fade(x, sr, sec=FADE):
    k = max(2, int(sec * sr))
    if len(x) < 2 * k:
        k = max(1, len(x) // 2)
    x[:k] *= np.linspace(0, 1, k)
    x[-k:] *= np.linspace(1, 0, k)
    return x


def rate_of(a, sr, n):
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return (n / v * 60 if v > 0 else 0.0), v


def proc_short(a, sr):
    """短句只用整体增益 + 限峰，不做句内包络。
    句内慢包络会把 2-4 词句子的起音/尾音改形（"What"→"But"）。"""
    y = a.astype(np.float32).copy()
    for _ in range(4):
        db = RB.rms_voiced_db(y, sr)
        if abs(db - U.TARGET) < 0.4:
            break
        y = y * (10 ** ((U.TARGET - db) / 20.0))
        y = U.limiter(y, sr)
    return y.astype(np.float32)


def stretch_file(src, dst, tempo):
    # 不加 transients=crisp：实测极短句起音被削，"In Wales"→"And well"
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality" % tempo,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def stretch_whole(a, sr, tempo, tag):
    """整条拉伸：保住句内连读与起音（短句必须走这条）。"""
    sp = os.path.join(TMP, "%s_whole.wav" % tag)
    sf.write(sp, a, sr, subtype="PCM_16")
    stretch_file(sp, sp + ".wav", tempo)
    b, _ = sf.read(sp + ".wav", dtype="float32", always_2d=True)
    return b.mean(1).astype(np.float32)


def stretch_segments(a, sr, tempo, tag):
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
    dst = "G:/_setup/ch123_v5"
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
        n = WORDS[k]
        tgt = target_of(n, who)
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        r0, v0 = rate_of(a, sr, n)
        dur = len(a) / sr
        nseg = len(RB.split_at_silence(a, sr, min_gap=0.12))
        tempo = 1.0
        if k in EXEMPT:
            tempo = EXEMPT[k]
        elif r0 > 0:
            tempo = min(TEMPO_MAX, max(tempo_floor(n, dur), tgt / r0))
            # 只有本来就要降速的，才考虑把不到 1 秒的撑到 1 秒
            if dur < 1.05 and tempo < 0.999:
                tempo = max(TEMPO_FLOOR, min(tempo, dur / 1.05))
        # 短句（<=6 词且 <2.2s）整条拉伸：保住起音与连读
        # 长句一律只拉语音段，段间停顿保持原样
        whole = (dur < 1.1) or (n <= 6 and dur < 2.2)
        if dry:
            print("%-5s %s %2d词 %5.0f → %5.0f  tempo %.3f  %.2fs→%.2fs  %s"
                  % (k, who, n, r0, r0 * tempo, tempo, dur, dur / tempo,
                     "整条" if whole else "分段"))
            continue

        # tempo 贴近 1 时的微调纯属有害：rubberband 会重排相位，
        # 实测 L059 拉到 0.967 就把 "died" 吞掉了 ⇒ 4% 以内不动
        if abs(tempo - 1.0) > 0.045:
            y = (stretch_whole(a, sr, tempo, k) if whole
                 else stretch_segments(a, sr, tempo, k))
        else:
            y = a
        # 一律用 proc_short：源文件已经过一轮句内包络归一，再压一次会吞掉弱词
        # （实测 L059 "grandfather died" 的 died 被抹掉）
        y = proc_short(y, sr)
        sf.write(os.path.join(dst, k + ".wav"), y, sr, subtype="PCM_16")
        r1, v1 = rate_of(y, sr, n)
        rows.append((k, who, n, r0, r1, tempo, len(y) / sr, v1))
        print("%-5s %s %2d词 %5.0f → %5.0f wpm  tempo %.3f  %5.2fs  发声%.2fs"
              % (k, who, n, r0, r1, tempo, len(y) / sr, v1), flush=True)

    for who in ("C", "E"):
        sub = [r for r in rows if r[1] == who]
        if not sub:
            continue
        print("\n== %s ==" % who)
        for lo, hi in ((1, 3), (4, 6), (7, 11), (12, 99)):
            s2 = [r for r in sub if lo <= r[2] <= hi]
            if not s2:
                continue
            v = [r[4] for r in s2]
            d = [r[7] for r in s2]
            print("  %2d-%2d词 n=%2d  %3.0f-%3.0f wpm (目标 %.0f)  发声 %.2f-%.2fs"
                  % (lo, hi, len(s2), min(v), max(v), target_of(lo, who), min(d), max(d)))


if __name__ == "__main__":
    main()
