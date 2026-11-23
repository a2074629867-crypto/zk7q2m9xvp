# -*- coding: utf-8 -*-
"""按 join 的 rows 把整章切回单元，测逐条 voiced RMS 跨度。"""
import sys, json
sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

def vrms(x, sr):
    db, _, hop = FP.frame_db(x, sr)
    thr = np.percentile(db, 90) - 25.0
    on = db > thr
    if on.sum() < 3:
        return np.nan
    seg = [x[i*hop:min(len(x), i*hop+hop)] for i in np.where(on)[0]]
    y = np.concatenate(seg).astype(np.float64)
    return 20*np.log10(np.sqrt((y**2).mean())+1e-12)

for wav, js in [("_chap_ch1_v4.wav", "_chap_ch1_v4.json"),
                ("_chap_ch1_v4b.wav", "_chap_ch1_v4b.json")]:
    x, sr = sf.read(wav, dtype="float32", always_2d=True); x = x.mean(1)
    rows = json.load(open(js, encoding="utf-8"))["rows"]
    pos = 0; vals = []
    for i, r in enumerate(rows):
        n = int(round(r["dur"] * sr))
        seg = x[pos:pos+n]
        vals.append((r["uid"], vrms(seg, sr)))
        pos += n
        if i < len(rows) - 1:
            pos += int(round(r["gap"] * sr))
    a = np.array([v for _, v in vals if not np.isnan(v)])
    print("%-20s p10 %.1f p50 %.1f p90 %.1f  跨度 %.2f dB  (%.1f~%.1f)" %
          (wav, np.percentile(a,10), np.median(a), np.percentile(a,90),
           a.max()-a.min(), a.min(), a.max()))
    off = sorted(vals, key=lambda t: t[1])[:3] + sorted(vals, key=lambda t: -t[1])[:3]
    print("   最轻/最响:", [(u, round(v,1)) for u, v in off])
