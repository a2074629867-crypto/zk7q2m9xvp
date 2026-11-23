# -*- coding: utf-8 -*-
"""L078「No. But...」补 But：从 L070（Yes, he did. But it had to be sold.）剪出 But 拼上。

L070 里 "But" 起音 ≈2.245s（浊爆破能量陡升），收声 ≈2.47s（/t/ 闭合后低谷）。
L078 现有内容 = "No."（0.08–0.35），其后 1.27–1.41 是残片，丢弃。
"""
import os
import sys

import numpy as np
import soundfile as sf

SRC_NO = "G:/_setup/ch123/L078.wav"
SRC_BUT = "G:/_setup/ch123/L070.wav"
OUT = "G:/_setup/_fix79/L078_but.wav"

NO_END = 0.40          # No. 收尾（含自带尾音）
BUT_T0, BUT_T1 = 2.222, 2.478
GAP = 0.30             # No. 与 But 之间的停顿
TAIL = 0.26            # 句尾留白（被打断感）
TARGET_DB = -22.5      # 对齐 L078 的 voiced 电平


def rd(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(1), sr


def voiced_db(a, sr):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ch123_rebuild as RB
    return RB.rms_voiced_db(a, sr)


def fade(a, sr, ms=12):
    n = int(ms / 1000.0 * sr)
    a[:n] *= np.linspace(0, 1, n)
    a[-n:] *= np.linspace(1, 0, n)
    return a


def main():
    no, sr = rd(SRC_NO)
    assert sr == 48000
    no = no[:int(NO_END * sr)]
    no_db = voiced_db(no, sr)
    no *= 10 ** ((TARGET_DB - no_db) / 20.0)

    but, sr2 = rd(SRC_BUT)
    but = but[int(BUT_T0 * sr2):int(BUT_T1 * sr2)].copy()
    if sr2 != sr:
        but = np.interp(np.arange(int(len(but) * sr / sr2)) / sr,
                        np.arange(len(but)) / sr2, but).astype(np.float32)
    but = fade(but, sr, 10)
    but_db = voiced_db(but, sr)
    but *= 10 ** ((TARGET_DB - but_db) / 20.0)

    out = np.concatenate([
        no,
        np.zeros(int(GAP * sr), dtype=np.float32),
        but,
        np.zeros(int(TAIL * sr), dtype=np.float32),
    ]).astype(np.float32)

    peak = np.abs(out).max()
    if peak > 0.92:
        out *= 0.92 / peak

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sf.write(OUT, out, sr, subtype="PCM_16")
    print("No  %.0f dB / But %.0f dB → 目标 %.1f dB" % (no_db, but_db, TARGET_DB))
    print("out %.2fs  peak %.3f → %s" % (len(out) / sr, np.abs(out).max(), OUT))


if __name__ == "__main__":
    main()
