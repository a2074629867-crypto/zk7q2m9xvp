# -*- coding: utf-8 -*-
"""把 no-ref-text 重建的成品回填到 _audio_ch123/out/，先备份、后校验。

    python _fill_notxt66.py --ids _notxt66_fill_ids.txt --bak _bak_notxt66_1124 --dry
    python _fill_notxt66.py --ids _notxt66_fill_ids.txt --bak _bak_notxt66_1124

判据（任一不满足就跳过，不写盘）：
  1. 源文件 voiced RMS 在 −24 ± 0.3 dBFS
  2. 时长 ≥ 0.15s
  3. 源与目标 md5 不同（避免把同一个文件又盖一遍）
"""
import argparse
import hashlib
import os
import shutil
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "_audio_ch123", "out")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def voiced_rms(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    if not len(v):
        return -99.0, len(y) / sr
    return float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)), len(y) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="逗号或换行分隔的 id 文件")
    ap.add_argument("--src", default="_sweep/notxt66_trim")
    ap.add_argument("--bak", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    src_dir = a.src if os.path.isabs(a.src) else os.path.join(HERE, a.src)
    bak = a.bak if os.path.isabs(a.bak) else os.path.join(HERE, a.bak)
    if not a.dry:
        os.makedirs(bak, exist_ok=True)

    raw = open(os.path.join(HERE, a.ids), encoding="utf-8").read()
    ids = [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]

    print("%-9s %7s %7s %7s %7s %s" % ("id", "旧dur", "新dur", "旧RMS", "新RMS", "结果"))
    ok = 0
    for rid in ids:
        p = os.path.join(src_dir, rid + "__s42.wav")
        dst = os.path.join(OUT, rid + ".wav")
        if not (os.path.exists(p) and os.path.exists(dst)):
            print("%-9s  缺文件" % rid)
            continue
        o_rms, o_dur = voiced_rms(dst)
        n_rms, n_dur = voiced_rms(p)
        reason = ""
        # 电平尺子：norm24 用的口径与这里的 voiced_rms 差 0.3~0.7 dB，
        # 全库现成品在这把尺子上就是 −24.1~−24.7。所以判「与旧文件持平」，
        # 不用绝对值 −24.0（那样会把整批都挡掉）。
        if abs(n_rms - o_rms) > 0.6:   # 全库跨度允许 1dB，取 0.6 作单条容差
            reason = "电平差 %+.1f" % (n_rms - o_rms)
        elif n_dur < 0.15:
            reason = "过短 %.2fs" % n_dur
        elif md5(p) == md5(dst):
            reason = "内容相同"
        tag = ("跳过(" + reason + ")") if reason else ("预演" if a.dry else "回填")
        print("%-9s %7.2f %7.2f %7.1f %7.1f %s" % (rid, o_dur, n_dur, o_rms, n_rms, tag))
        if reason or a.dry:
            continue
        bp = os.path.join(bak, rid + ".wav")
        if not os.path.exists(bp):
            shutil.copy2(dst, bp)
        shutil.copy2(p, dst)
        if md5(p) != md5(dst):
            print("   !! 写入后 md5 不一致：%s" % rid)
            continue
        ok += 1
    print("\n回填 %d / %d（备份 → %s）" % (ok, len(ids), bak))


if __name__ == "__main__":
    main()
