# -*- coding: utf-8 -*-
"""扫「伪尾噪」：静音缺口之后又冒出的无基频噪声。

与普通尾辅音的区别（这是判据的核心）：
- 真辅音（s/t/f/sh）紧接有声段，**中间没有静音缺口**；
- 伪影一定出现在**一段 >=15ms 的近静音之后**，且自身无基频（periodicity<0.35）。

输出每条的：缺口位置、噪声段起止、时长、是否在文件末尾。
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

GAP_DB = -45.0      # 近静音门限（绝对）
GAP_MIN = 0.015     # 缺口最短 15ms
NOI_DB = -42.0      # 噪声段最低电平
NOI_MIN = 0.040     # 噪声段最短 40ms
PER_THR = 0.35


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
        if db[i] < NOI_DB:
            continue
        f = seg[i] - seg[i].mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        if b < len(ac):
            per[i] = ac[int(np.argmax(ac[a:b])) + a] / (ac[0] + 1e-12)
    return db, per, h / sr


def analyze(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    db, per, step = frames(y, sr)

    hits = []
    i = 0
    n = len(db)
    while i < n:
        # 找近静音缺口
        if db[i] < GAP_DB:
            j = i
            while j < n and db[j] < GAP_DB:
                j += 1
            gap = (j - i) * step
            if gap >= GAP_MIN and j < n:
                # 缺口后面紧跟的无基频段
                k = j
                while k < n and db[k] >= NOI_DB and per[k] < PER_THR:
                    k += 1
                leng = (k - j) * step
                if leng >= NOI_MIN:
                    hits.append({"gap": [round(i * step, 3), round(j * step, 3)],
                                 "noise": [round(j * step, 3), round(k * step, 3)],
                                 "gap_s": round(gap, 3), "noise_s": round(leng, 3),
                                 "at_end": bool((k >= n - 1) and (dur - k * step < 0.05))})
                i = max(k, i + 1)
                continue
            i = j
            continue
        i += 1
    return {"dur": round(dur, 2), "hits": hits,
            "n": len(hits), "tail": any(h["at_end"] for h in hits)}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "_audio_ch123/out"
    out = sys.argv[2] if len(sys.argv) > 2 else "_scan_falsetail.json"
    files = sorted(glob.glob(os.path.join(d, "*.wav")))
    res = {}
    for k, f in enumerate(files):
        rid = os.path.basename(f)[:-4]
        try:
            res[rid] = analyze(f)
        except Exception as e:
            res[rid] = {"err": str(e), "hits": [], "n": 0, "tail": False}
        if (k + 1) % 200 == 0:
            print("  %d/%d" % (k + 1, len(files)))
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    hit = {k: v for k, v in res.items() if v.get("n")}
    tail = {k: v for k, v in hit.items() if v.get("tail")}
    mid = {k: v for k, v in hit.items() if not v.get("tail")}
    print("\n扫描 %d 条" % len(res))
    print("  有伪尾噪（任一处）：%d 条" % len(hit))
    print("  出现在文件末尾    ：%d 条" % len(tail))
    print("  只在句中          ：%d 条" % len(mid))
    tot = sum(h["noise_s"] for v in hit.values() for h in v["hits"])
    print("  伪噪总时长 %.1fs" % tot)
    order = sorted(tail, key=lambda k: -max(h["noise_s"] for h in res[k]["hits"]))
    print("\n  末尾伪噪最长的 15 条：")
    for k in order[:15]:
        h = max(res[k]["hits"], key=lambda x: x["noise_s"])
        print("    %-9s gap %.3fs + 噪声 %.3fs  (dur %.2fs)" % (k, h["gap_s"], h["noise_s"], res[k]["dur"]))
    json.dump({"tail": sorted(tail), "mid": sorted(mid)}, open("_scan_falsetail_hit.json", "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
