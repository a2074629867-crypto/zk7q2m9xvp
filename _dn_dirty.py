# -*- coding: utf-8 -*-
"""_dn_dirty.py —— 对「底噪偏高」的成品做定向除噪 A/B（arnndn）

问的问题只有一个：除噪压掉的是**噪声**还是**语音**？
  用 wav2vec2 无语言模型对齐的「词均分」做尺子：
    除噪后词均分不降（或降 <0.5）        → 压的是噪声，安全
    除噪后出现新的低分词 / 均分掉 >0.5   → 吃语音，不许推全库
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG

FF = "E:/tool/oopz/ffmpeg.exe"
OUT = "G:/_setup/_dn_dirty"
REPORT = "G:/_setup/_dn_dirty.json"


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + (len(y) - w) // h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    zero = np.abs(seg).max(1) == 0
    return 20 * np.log10(e), zero


def hf_ratio(y, sr, lo=6000, hi=12000):
    n, hop = 1024, 512
    if len(y) < n * 2:
        return 0.0
    win = np.hanning(n)
    f = np.fft.rfftfreq(n, 1 / sr)
    mh = (f >= lo) & (f < hi)
    ah = at = 0.0
    for i in range(0, 1 + (len(y) - n) // hop, 4):
        P = np.abs(np.fft.rfft(y[i * hop:i * hop + n] * win)) ** 2
        ah += P[mh].sum()
        at += P.sum()
    return float(ah / max(at, 1e-20))


def meas(p):
    y, sr = sf.read(p, dtype="float64", always_2d=True)
    y = y.mean(1)
    db, zero = frame_db(y, sr)
    nz = db[~zero]
    return {"floor_nz": round(float(np.percentile(nz, 10)), 1) if len(nz) else -240.0,
            "hf": round(hf_ratio(y, sr), 5),
            "dur": round(len(y) / sr, 3)}


def asr(proc, model, wav, text):
    r = AG.align(proc, model, wav, text)
    if r is None:
        return None
    bad, allw = AG.judge(r)
    import _pick52 as PK
    gold = PK.norm_words(text)
    hyp = PK.norm_words(r["greedy"])
    return {"cov": round(PK.coverage(gold, hyp), 3), "nword": len(allw),
            "mean_all": round(float(np.mean([w["mean"] for w in allw])), 2) if allw else -99,
            "bad": [b_["word"] for b_ in bad],
            "greedy": r["greedy"][:120]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--thr", type=float, default=-45.0)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    scan = json.load(open("G:/_setup/_dn_scan.json", encoding="utf-8"))
    sys.path.insert(0, "G:/_setup")
    import _calm_gate as CG
    plan = CG.load_plan()
    cand = [(k, v["floor_nz"]) for k, v in scan.items()
            if v["floor_nz"] > a.thr and k in plan]
    cand.sort(key=lambda x: -x[1])
    cand = cand[:a.n]
    print("选中 %d 条最脏：%s" % (len(cand), [(k, f) for k, f in cand]), flush=True)

    proc, model = AG.load_model()
    rep = {}
    for rid, fl in cand:
        src = f"G:/_setup/_audio_ch123/out/{rid}.wav"
        if not os.path.exists(src):
            continue
        text = plan[rid].get("text") or ""
        dst = os.path.join(OUT, rid + "_arnndn.wav")
        r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                            "-af", "arnndn=m=std.rnnn", "-ar", "48000", dst],
                           cwd="G:/_setup", capture_output=True, text=True)
        if r.returncode != 0:
            print(rid, "ffmpeg FAIL", r.stderr[-200:], flush=True)
            continue
        m0, m1 = meas(src), meas(dst)
        s0 = asr(proc, model, src, text)
        s1 = asr(proc, model, dst, text)
        if not s0 or not s1:
            print(rid, "align FAIL", flush=True)
            continue
        dfl = m1["floor_nz"] - m0["floor_nz"]
        dhf = (m1["hf"] / m0["hf"] - 1) * 100 if m0["hf"] else 0
        dcov = s1["cov"] - s0["cov"]
        dmean = s1["mean_all"] - s0["mean_all"]
        newbad = [w for w in s1["bad"] if w not in s0["bad"]]
        rep[rid] = {"floor0": m0["floor_nz"], "floor1": m1["floor_nz"], "d_floor": round(dfl, 1),
                    "d_hf_pct": round(dhf, 1), "dur": m0["dur"],
                    "cov0": s0["cov"], "cov1": s1["cov"], "d_cov": round(dcov, 3),
                    "mean0": s0["mean_all"], "mean1": s1["mean_all"], "d_mean": round(dmean, 2),
                    "new_bad": newbad, "bad0": s0["bad"]}
        flag = "OK " if (dcov >= -0.01 and dmean >= -0.5 and not newbad) else "WARN"
        print("%-9s %s floor %.1f→%.1f (%+.1f)  hf %+.1f%%  cov %.3f→%.3f  "
              "均分 %.2f→%.2f  新低分 %s"
              % (rid, flag, m0["floor_nz"], m1["floor_nz"], dfl, dhf,
                 s0["cov"], s1["cov"], s0["mean_all"], s1["mean_all"], newbad), flush=True)

    json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for v in rep.values()
             if v["d_cov"] >= -0.01 and v["d_mean"] >= -0.5 and not v["new_bad"])
    print("\n修完 %d 条：OK %d / WARN %d" % (len(rep), ok, len(rep) - ok))
    print("saved", REPORT)


if __name__ == "__main__":
    main()
