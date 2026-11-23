# -*- coding: utf-8 -*-
"""整章统计：总时长 / voiced 时长 / 语音占比 / voiced wpm / 停顿分布。"""
import sys
sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf
import mt_final_pause as FP

WORDS = {"ch1": 2430}

def stat(path, words):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    db, nfl, hop = FP.frame_db(x, sr)
    thr = np.percentile(db, 90) - 25.0
    on = db > thr
    voiced = float(on.sum()) * hop / sr
    tot = len(x) / sr
    # 静音段
    gaps, run, st = [], 0, 0
    for i, v in enumerate(on):
        if not v:
            if run == 0:
                st = i
            run += 1
        else:
            if run:
                g = run * hop / sr
                if g >= 0.30:
                    gaps.append((st * hop / sr, g))
            run = 0
    if run:
        g = run * hop / sr
        if g >= 0.30:
            gaps.append((st * hop / sr, g))
    gl = np.array([g for _, g in gaps])
    return dict(path=path, tot=tot, voiced=voiced,
                ratio=100 * voiced / tot,
                wpm=words / voiced * 60,
                span_wpm=words / tot * 60,
                ngap=len(gl),
                g_p50=float(np.median(gl)) if len(gl) else 0,
                g_p90=float(np.percentile(gl, 90)) if len(gl) else 0,
                g_max=float(gl.max()) if len(gl) else 0,
                g_sum=float(gl.sum()) if len(gl) else 0)

rows = []
for f in ["G:/_setup/_chap_ch1_soar_a.wav", "G:/_setup/_chap_ch1_soar_b.wav"]:
    try:
        rows.append(stat(f, WORDS["ch1"]))
    except Exception as e:
        print("ERR", f, e)

print("%-22s %7s %7s %6s %6s %6s %6s %5s %5s %5s" %
      ("文件", "总时长", "voiced", "占比%", "voiced", "span", "停顿s", "n", "p50", "p90"))
for r in rows:
    print("%-22s %7.1f %7.1f %6.1f %6.0f %6.0f %6.1f %5d %5.2f %5.2f" %
          (r["path"].replace("_chap_ch1_", ""), r["tot"], r["voiced"], r["ratio"],
           r["wpm"], r["span_wpm"], r["g_sum"], r["ngap"], r["g_p50"], r["g_p90"]))
