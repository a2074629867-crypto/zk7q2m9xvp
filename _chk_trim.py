# -*- coding: utf-8 -*-
"""裁边质检：开头/结尾是否有残余语音（切在语音上会听到咔哒）。"""
import sys, glob, os
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

rows = []
for p in sorted(glob.glob("_mt_final_raw_trim/*.wav")):
    x, sr = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    n = int(0.03 * sr)
    hp = float(np.abs(x[:n]).max())
    tp = float(np.abs(x[-n:]).max())
    # 头 5ms 内的能量占比（淡入区）
    rows.append((os.path.basename(p)[:-4], hp, tp, len(x) / sr))

hp = np.array([r[1] for r in rows]); tp = np.array([r[2] for r in rows])
print("条数", len(rows))
print("头30ms峰值  p50 %.3f p90 %.3f max %.3f" % (np.median(hp), np.percentile(hp, 90), hp.max()))
print("尾30ms峰值  p50 %.3f p90 %.3f max %.3f" % (np.median(tp), np.percentile(tp, 90), tp.max()))
bad_h = [r for r in rows if r[1] > 0.15]
bad_t = [r for r in rows if r[2] > 0.15]
print("头>0.15 的 %d 条: %s" % (len(bad_h), [r[0] for r in bad_h][:8]))
print("尾>0.15 的 %d 条: %s" % (len(bad_t), [r[0] for r in bad_t][:8]))
print("最短单元 %.2fs  %s" % (min(r[3] for r in rows), min(rows, key=lambda r: r[3])[0]))
