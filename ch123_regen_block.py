# -*- coding: utf-8 -*-
"""按"一次整句生成 + 无 emo + 停顿重建 + 轻度降速"重做指定条目。

流程：
  1) dots tts 整句生成（不加 emo，音色只有一层，语调曲线连续）
  2) 按句间静音切段，逐段电平对齐，再按原文标点插入停顿
  3) 若语速超过目标，rubberband 降速（保音高，formant 保持）
  4) 写回 ch123/<key>.wav，旧文件备份到 ch123_old/
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf

import bk_resplit as R
import ch123_level as L
import ch123_rebuild as RB
from ch123_plan import REFS

FF = "E:/tool/oopz/ffmpeg.exe"
OUT = "G:/_setup/ch123"
TMP = "G:/_setup/_regen"
BAK = "G:/_setup/ch123_old"
TARGET_WPM = 200.0

# key, 说话人, 文本, 段间停顿列表（None = 沿用原生成）
JOBS = [
    ("L075", "C", "Oh, yes. Well, a bit. He was a pilot, once. He was in the Battle of Britain.", [0.38, 0.34, 0.42]),
    ("L076", "C", "I've got a picture of him.", None),
    ("L083", "C", "Here's the picture. Look, that's my father.", [0.45]),
    ("L085", "C", "A few years ago. I was about five. Or six.", [0.40, 0.32]),
    ("L087", "C", "I don't know. Quite old, I suppose. Look, then, there's the photograph.", [0.40, 0.36]),
]


def tempo_to(wav_in, wav_out, tempo):
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", wav_in,
                    "-af", "rubberband=tempo=%.3f:pitchq=quality" % tempo,
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", wav_out], check=True)


def run(key, who, text, gaps, target=TARGET_WPM):
    ref, rtext = REFS[who]
    raw = os.path.join(TMP, "%s_raw.wav" % key)
    os.makedirs(TMP, exist_ok=True)
    n = len(text.split())
    mt = max(220, int(n * 30) + 180)
    ok = R.gen(text, ref, rtext, mt, raw, [])
    if not ok:
        time.sleep(15)
        ok = R.gen(text, ref, rtext, mt, raw, [])
    if not ok:
        print("%s 生成失败" % key, flush=True)
        return None

    a, sr = sf.read(raw, dtype="float32", always_2d=True)
    a = a.mean(1)
    y, info = RB.rebuild(a, sr, gaps=gaps, target_db=-24.0, max_level_db=6.0)
    wpm = n / (len(y) / sr) * 60
    tempo = 1.0
    if wpm > target + 5:
        tempo = max(0.78, target / wpm)
        mid = os.path.join(TMP, "%s_reb.wav" % key)
        sf.write(mid, y, sr, subtype="PCM_16")
        tempo_to(mid, raw + ".slow.wav", tempo)
        y, sr = sf.read(raw + ".slow.wav", dtype="float32", always_2d=True)
        y = y.mean(1)
        os.remove(mid)
    d = len(y) / sr
    pk = float(np.max(np.abs(y)))
    if pk > 0.95:
        y *= 0.95 / pk
    os.makedirs(BAK, exist_ok=True)
    dst = os.path.join(OUT, "%s.wav" % key)
    if os.path.exists(dst):
        shutil.copy2(dst, os.path.join(BAK, "%s.wav" % key))
    sf.write(dst, y, sr, subtype="PCM_16")
    print("%-5s %5.2fs %.0f wpm tempo %.2f 段%d %s" % (key, d, n / d * 60, tempo, len(info),
                                                      " ".join("%.0fHz/%.0fdB" % (0, x[3]) for x in info)),
          flush=True)
    return dst


if __name__ == "__main__":
    keys = sys.argv[1:]
    for key, who, text, gaps in JOBS:
        if keys and key not in keys:
            continue
        run(key, who, text, gaps)
        time.sleep(12)
