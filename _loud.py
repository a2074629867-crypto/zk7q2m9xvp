# -*- coding: utf-8 -*-
"""_loud.py —— 审听页专用响度对齐（不改台账，只产出归一化副本）

口径沿用 `_dn_uniform.norm_rms`：voiced 帧（>p70）RMS 归一到 -24 dBFS。
理由：全文件 RMS 会被首尾静音和停顿带偏，听感大小跟 voiced RMS 走。

用法：
    from _loud import to_uniform
    p2, info = to_uniform(src_wav, "G:/_setup/_pool_norm", target_db=-24.0)
    info = {"gain_db":..., "voiced_db":..., "peak":...}
"""
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _dn_uniform as DU  # noqa: E402


def voiced_db(y, sr):
    db, h, w = DU.frame_db(y, sr)
    m = db > np.percentile(db, 70)
    cnt = 1 + max(0, (len(y) - w) // h)
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(cnt)[:, None], 0, len(y) - 1)
    seg = y[idx][m]
    r = np.sqrt((seg ** 2).mean()) + 1e-12
    return 20 * np.log10(r)


def to_uniform(src, out_dir, target_db=-24.0, force=False):
    """返回 (归一化文件路径, 信息 dict)。同参数已存在则复用。"""
    y, sr = sf.read(src, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    v0 = voiced_db(y, sr)
    yn = DU.norm_rms(y, sr, target_db)
    pk = float(np.abs(yn).max())
    clipped = False
    if pk > 0.995:                      # 归一后爆表 → 整体回退，保住不削波
        yn = yn * (0.995 / pk)
        clipped = True
    pk = float(np.abs(yn).max())
    v1 = voiced_db(yn, sr)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    tag = os.path.basename(os.path.dirname(src))
    dst = os.path.join(out_dir, "%s__%s.wav" % (tag, stem))
    if force or not os.path.exists(dst):
        sf.write(dst, yn, sr, subtype="PCM_16")
    return dst, {"src": src, "gain_db": v1 - v0, "voiced_db": v1,
                 "peak": pk, "clipped": clipped, "dst": dst}


if __name__ == "__main__":
    import glob
    import json
    ap_dir = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_pool2/c3_0853"
    out = sys.argv[2] if len(sys.argv) > 2 else "G:/_setup/_pool_norm"
    rep = {}
    for f in sorted(glob.glob(os.path.join(ap_dir, "*.wav"))):
        p, info = to_uniform(f, out, force=True)
        rep[os.path.basename(f)] = info
        print("%-10s gain %+6.1f dB  voiced %.1f  peak %.2f%s"
              % (os.path.basename(f), info["gain_db"], info["voiced_db"],
                 info["peak"], "  [回退]" if info["clipped"] else ""))
    json.dump(rep, open("G:/_setup/_loud_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
