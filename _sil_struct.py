# -*- coding: utf-8 -*-
"""对比新旧 take 的静音结构：前导 / 尾随 / 内部停顿。"""
import sys, glob, os, json
sys.path.insert(0, "D:/py_libs"); sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]

def sil(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True); x = x.mean(1)
    db, n, hop = FP.frame_db(x, sr)
    if len(db) == 0: return None
    on = db > (np.percentile(db, 90) - 25.0)
    idx = np.where(on)[0]
    if len(idx) < 5: return None
    h = hop / sr
    head = idx[0] * h
    tail = (len(db) - 1 - idx[-1]) * h
    gaps = np.diff(idx) * h
    inner = gaps[gaps >= 0.10]
    return dict(head=head, tail=tail, ninner=len(inner), inner_sum=float(inner.sum()),
                dur=len(x)/sr)

for tag, dirs in (("旧 Edit q8_0", ["_mt_raw_s42","_mt_raw_s1234"]),
                  ("新 SOAR bf16", ["_mt_raw_ch1_s42","_mt_raw_ch1_s1234"])):
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(d+"/*.wav")):
            uid = os.path.basename(p)[:-4]
            if uid not in S or S[uid].get("ch") != "ch1": continue
            m = sil(p)
            if m: rows.append(m)
    if not rows: print(tag, "无数据"); continue
    a = lambda k: np.array([r[k] for r in rows])
    print("%-14s n=%3d  前导 p50 %.2f p90 %.2f max %.2f | 尾随 p50 %.2f p90 %.2f | "
          "内部停顿 个数 %.1f 合计 %.2f s | 空白占 %.0f%%"
          % (tag, len(rows),
             np.median(a("head")), np.percentile(a("head"),90), a("head").max(),
             np.median(a("tail")), np.percentile(a("tail"),90),
             a("ninner").mean(), a("inner_sum").mean(),
             100*(a("head")+a("tail")+a("inner_sum")).sum()/a("dur").sum()))
