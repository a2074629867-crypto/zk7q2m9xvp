# -*- coding: utf-8 -*-
import sys, glob, os, json
sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

def two(x, sr):
    db, _, hop = FP.frame_db(x, sr)
    thr = np.percentile(db, 90) - 25.0
    on = db > thr
    seg = [x[i*hop:min(len(x), i*hop+hop)] for i in np.where(on)[0]]
    y = np.concatenate(seg).astype(np.float64) if seg else np.zeros(1)
    vad = 20*np.log10(np.sqrt((y**2).mean())+1e-12)
    # 绝对：全程去最低 10% 帧
    cut = np.percentile(db, 10)
    on2 = db > max(cut, -70)
    seg2 = [x[i*hop:min(len(x), i*hop+hop)] for i in np.where(on2)[0]]
    y2 = np.concatenate(seg2).astype(np.float64) if seg2 else np.zeros(1)
    absd = 20*np.log10(np.sqrt((y2**2).mean())+1e-12)
    return vad, absd, len(x)/sr

rows=[]
for p in sorted(glob.glob("_mt_final_raw_trim/*.wav")):
    x, sr = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    v, a, d = two(x, sr)
    rows.append((os.path.basename(p)[:-4], v, a, d))

v = np.array([r[1] for r in rows]); a = np.array([r[2] for r in rows])
d = np.array([r[3] for r in rows])
print("VAD口径   p10/p50/p90 = %.1f / %.1f / %.1f  跨度 %.2f" % (np.percentile(v,10), np.median(v), np.percentile(v,90), v.max()-v.min()))
print("绝对口径  p10/p50/p90 = %.1f / %.1f / %.1f  跨度 %.2f" % (np.percentile(a,10), np.median(a), np.percentile(a,90), a.max()-a.min()))
print()
print("最短10条（按时长）:")
for r in sorted(rows, key=lambda r: r[3])[:10]:
    print("  %s  dur %.2f  vad %.1f  绝对 %.1f" % r)
print("VAD最低10条:")
for r in sorted(rows, key=lambda r: r[1])[:10]:
    print("  %s  dur %.2f  vad %.1f  绝对 %.1f" % r)
