# -*- coding: utf-8 -*-
"""裁掉短句首尾多余静音，再归一到 -24 dBFS。

为什么需要：`c3_0632` 交付件 1.96s 里尾部有 1.56s 静音（生成时带的尾巴），
silent 比 0.56 被判 clean 挂 —— 不是音频坏，是**尾巴没裁**。

用法：G:/Python310/python.exe _trim_sil.py --ids c3_0632 [--head 0.03 --tail 0.06]
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, "G:/_setup")

import numpy as np
import soundfile as sf

from narr_gate_phys import voiced_db

S = "G:/_setup"
OUT = os.path.join(S, "_audio_ch123", "out")
PAU = os.path.join(S, "_audio_ch123", "out_paused")
BAK = os.path.join(S, "_bak_trimtail_1120")


def frames(y, sr, fl=0.025, hp=0.020, thr=-45.0):
    n = 1 + (len(y) - int(fl * sr)) // int(hp * sr)
    idx = np.arange(int(fl * sr))[None, :] + int(hp * sr) * np.arange(n)[:, None]
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    return db > thr, hp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--head", type=float, default=0.03)
    ap.add_argument("--tail", type=float, default=0.06)
    a = ap.parse_args()
    os.makedirs(BAK, exist_ok=True)
    for rid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        p = os.path.join(PAU, rid + ".wav")
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        vo, hp = frames(y, sr)
        if not vo.any():
            print(rid, "全静音，跳过")
            continue
        i0, i1 = int(np.argmax(vo)), len(vo) - int(np.argmax(vo[::-1])) - 1
        s = max(0, int((i0 * hp - a.head) * sr))
        e = min(len(y), int(((i1 + 1) * hp + a.tail) * sr))
        y2 = y[s:e].astype("float32")
        # 20ms 淡入淡出，避免切点咔哒
        k = int(0.02 * sr)
        if len(y2) > 2 * k:
            y2[:k] *= np.linspace(0, 1, k, dtype="float32")
            y2[-k:] *= np.linspace(1, 0, k, dtype="float32")
        lv, _, _ = voiced_db(np.ascontiguousarray(y2), sr)
        if lv is not None:
            g = 10 ** ((-24.0 - lv) / 20.0)
            if float(np.abs(y2).max()) * g > 0.97:
                g = 0.97 / float(np.abs(y2).max())
            y2 = (y2 * g).astype("float32")
        lv2, _, _ = voiced_db(np.ascontiguousarray(y2), sr)
        for d in (OUT, PAU):
            q = os.path.join(d, rid + ".wav")
            if os.path.exists(q):
                shutil.copy2(q, os.path.join(BAK, os.path.basename(d) + "_" + rid + ".wav"))
            sf.write(q, y2, sr, subtype="PCM_16")
        print("%s %.2fs -> %.2fs  RMS %.2f -> %.2f" % (rid, len(y) / sr, len(y2) / sr, lv or 0, lv2 or 0))


if __name__ == "__main__":
    main()
