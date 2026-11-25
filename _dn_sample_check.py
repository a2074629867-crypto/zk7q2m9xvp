# -*- coding: utf-8 -*-
"""抽样验证 demucs 对成品的损伤：底噪 / SNR / 声纹。"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")
import _dn_uniform as DU

IDS = ["c2_0297", "c2_0447", "c2_0356", "c1_0154", "c3_0656", "c2_0293", "c1_0140", "c1_0042"]


def main():
    print("%-9s %7s %7s %7s %7s %6s %6s" %
          ("id", "底噪前", "底噪后", "SNR前", "SNR后", "峰", "dur"))
    rows = []
    for i in IDS:
        a = "G:/_setup/_audio_ch123/out/%s.wav" % i
        b = "G:/_setup/_dn_demucs/htdemucs/%s/vocals.wav" % i
        if not (os.path.exists(a) and os.path.exists(b)):
            print("%-9s 缺" % i)
            continue
        ya, sra = sf.read(a, dtype="float32")
        yb, srb = sf.read(b, dtype="float32")
        if ya.ndim > 1:
            ya = ya.mean(1)
        if yb.ndim > 1:
            yb = yb.mean(1)
        fa, _, _ = DU.floor_db_of(ya, sra)
        fb, _, _ = DU.floor_db_of(yb, srb)
        sa, sb = DU.snr_of(ya, sra), DU.snr_of(yb, srb)
        print("%-9s %7.1f %7.1f %7.1f %7.1f %6.2f %6.2f" %
              (i, fa, fb, sa, sb, float(np.abs(yb).max()), len(yb) / srb))
        rows.append((i, fa, fb, sa, sb))
    if rows:
        d = [r[2] - r[1] for r in rows]
        print("\n底噪平均降 %.1f dB，最小降 %.1f，最大降 %.1f" %
              (np.mean(d), min(d), max(d)))


if __name__ == "__main__":
    main()
