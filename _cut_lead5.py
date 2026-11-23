# -*- coding: utf-8 -*-
"""手工指定切点：把开头多念的参考文本整段切掉（本轮 5 条的收尾）。

自动判 lead 在这 5 条上不可靠（wav2vec2 贪心解码把 THAT'S 读成 HAT、
把参考句读成 RICHEL HITSELF…），所以直接按逐词时间戳人工定切点。
切完重新跑 w2v 复检，插入词数必须归零。
"""
import io
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _pick52 as PK
import _calm_gate as CG

D = "G:/_setup/_audio_ch123/out_deliver"
BAK = "G:/_setup/_bak_lead2_1121"

# id -> (切点秒, 说明)
CUTS = {
    "c2_0445": (4.39, "RICHEL HITSELF … RESERVED MAN | WELL …"),
    "c1_0149": (2.09, "MY FATHER WAS A RESERVED MAN | IT'S EASY …"),
    "c2_0430": (1.09, "UT HIS EMBRACE | DO NOT ANSWER …"),
    "c1_0046": (3.23, "SI WAS LOOKING … SORRY FOR ME | YES"),
}


def cut(rid, sec):
    p = os.path.join(D, rid + ".wav")
    y, sr = sf.read(p, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    os.makedirs(BAK, exist_ok=True)
    bak = os.path.join(BAK, rid + ".wav")
    if not os.path.exists(bak):
        shutil.copyfile(p, bak)
    c = int(sec * sr)
    z = y[c:].copy()
    f = max(1, int(0.02 * sr))
    z[:f] *= np.linspace(0, 1, f)
    if abs(z).max() > 0.98:
        z = z * (0.98 / abs(z).max())
    sf.write(p, z, sr, subtype="PCM_16")
    return round(len(y) / sr, 2), round(len(z) / sr, 2)


def main():
    for rid, (sec, why) in CUTS.items():
        a, b = cut(rid, sec)
        print("%-9s %.2fs → %.2fs   切掉：%s" % (rid, a, b, why))
    # c2_0404 不是 lead，是句子中间复读，直接换用 emo 候选（那一版解码干净）
    src = "_sweep/camp9/c2_0404__emo__s42.wav"
    dst = os.path.join(D, "c2_0404.wav")
    if os.path.exists(src):
        shutil.copyfile(dst, os.path.join(BAK, "c2_0404.wav"))
        shutil.copyfile(src, dst)
        print("c2_0404   换成 emo 候选（解码 IT IS MY WINDOW NOW，零插入）")


if __name__ == "__main__":
    main()
