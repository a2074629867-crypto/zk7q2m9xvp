# -*- coding: utf-8 -*-
"""终版：扫「假尾」（去掉会误砍真语音的那类）。

四条同时满足才算：
1. 前有「断点」：rms 掉到 −42dBFS 以下 ≥12ms；
2. 之后 25ms 帧的无基频段（periodicity 中位 <0.40）连续 ≥100ms；
3. 该段**电平平稳**：rms 的变异系数 CV <0.30（真人声/气声都有明显包络，不会这么平）；
4. 该段平均 rms > −40dBFS（听得见）。

第 3 条是关键：c1_0182 的 2.48~2.71s 虽然无基频，但 rms 走 0.027→0.123→0.014，CV=0.61，
是有包络的人声，不能砍；c2_0276 的 0.37~0.57s 是 0.038/0.039/0.041 一条直线，CV=0.06，是伪影。
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

GAP_DB, GAP_MIN = -42.0, 0.012
NOI_MIN, PER_MED, CV_MAX, RMS_MIN = 0.100, 0.40, 0.30, 0.010
VOI_DB, VOI_PER = -40.0, 0.45


def frames(y, sr, win=0.025, hop=0.010):
    w, h = int(win * sr), int(hop * sr)
    n = 1 + max(0, (len(y) - w)) // h
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(n)[:, None], 0, len(y) - 1)
    seg = y[idx]
    rms = np.sqrt((seg ** 2).mean(1))
    db = 20 * np.log10(rms + 1e-12)
    per = np.zeros(n)
    a, b = int(sr / 400), int(sr / 60)
    for i in range(n):
        if db[i] < VOI_DB:
            continue
        f = seg[i] - seg[i].mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        if b < len(ac):
            per[i] = ac[int(np.argmax(ac[a:b])) + a] / (ac[0] + 1e-12)
    return db, per, rms, h / sr


def analyze(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    db, per, rms, step = frames(y, sr)
    n = len(db)
    zeros = int((np.abs(y) == 0).sum())

    hits = []
    i = 0
    while i < n - 1:
        if db[i] < GAP_DB:
            j = i
            while j < n and db[j] < GAP_DB:
                j += 1
            if (j - i) * step >= GAP_MIN and j < n:
                k = j
                while k < n and db[k] > GAP_DB and per[k] < PER_MED:
                    k += 1
                for e in range(k, j, -1):        # 收紧到最后一个仍低周期且有声的帧
                    if rms[e - 1] > RMS_MIN:
                        k = e
                        break
                leng = (k - j) * step
                if leng >= NOI_MIN:
                    seg = rms[j:k]
                    cv = float(seg.std() / (seg.mean() + 1e-12))
                    if cv < CV_MAX and seg.mean() > RMS_MIN:
                        hits.append({"gap": round(i * step, 3), "start": round(j * step, 3),
                                     "end": round(k * step, 3), "len": round(leng, 3),
                                     "cv": round(cv, 3),
                                     "per": round(float(np.median(per[j:k])), 3),
                                     "at_end": bool(dur - k * step < 0.12)})
                i = max(k, i + 1)
                continue
            i = j
            continue
        i += 1
    return {"dur": round(dur, 2), "hits": hits, "n": len(hits), "zeros": zeros}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "_audio_ch123/out"
    out = sys.argv[2] if len(sys.argv) > 2 else "_scan_tail3.json"
    files = sorted(glob.glob(os.path.join(d, "*.wav")))
    res = {}
    for k, f in enumerate(files):
        rid = os.path.basename(f)[:-4]
        try:
            res[rid] = analyze(f)
        except Exception as e:
            res[rid] = {"err": str(e), "hits": [], "n": 0}
        if (k + 1) % 200 == 0:
            print("  %d/%d" % (k + 1, len(files)))
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    hit = {k: v for k, v in res.items() if v.get("n")}
    tail = [k for k, v in hit.items() if any(h["at_end"] for h in v["hits"])]
    print("\n扫描 %d 条" % len(res))
    print("  命中 %d 条 | 其中在文件末尾 %d 条" % (len(hit), len(tail)))
    print("  伪噪总时长 %.2fs" % sum(h["len"] for v in hit.values() for h in v["hits"]))
    order = sorted(hit, key=lambda k: -max(h["len"] for h in hit[k]["hits"]))
    print("\n  %-9s %7s %7s %6s %6s %5s" % ("id", "dur", "假尾s", "end", "cv", "per"))
    for k in order:
        h = max(hit[k]["hits"], key=lambda x: x["len"])
        print("  %-9s %7.2f %7.3f %6.2f %6.2f %5.2f%s" %
              (k, hit[k]["dur"], h["len"], h["end"], h["cv"], h["per"],
               "  ← 末尾" if h["at_end"] else ""))
    json.dump({"all": sorted(hit), "tail": sorted(tail)},
              open("_scan_tail3_hit.json", "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
