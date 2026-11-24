# -*- coding: utf-8 -*-
"""扫「假尾」：最后一个浊音帧之后，出现「掉到近静音 → 又升起的无基频稳定噪声」。

为什么这个判据能区分真假尾辅音：
- 真尾辅音（s/z/f/θ）从元音**连续衰减**过来，中间不会掉到 −42dBFS 再升起来；
- 假尾一定有一个「断点」：要么是精确数字零，要么是掉到近静音 10ms 以上再重新起音；
- 假尾自身是无基频（periodicity<0.35）且电平平稳的噪声/蜂鸣。
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

GAP_DB = -42.0
GAP_MIN = 0.010
NOI_MIN = 0.050
PER_THR = 0.35
VOI_DB = -40.0
VOI_PER = 0.45


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
    return db, per, h / sr


def analyze(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    db, per, step = frames(y, sr)
    n = len(db)

    voi = np.where((per > VOI_PER) & (db > VOI_DB))[0]
    if not len(voi):
        return {"dur": round(dur, 2), "tail_art": 0.0, "kind": "no_voiced", "zeros": 0}
    last = int(voi[-1])

    zeros = int((np.abs(y) == 0).sum())
    # 从 last 之后找「掉落再升起」
    art = 0.0
    kind = ""
    i = last + 1
    while i < n - 1:
        if db[i] < GAP_DB:
            j = i
            while j < n and db[j] < GAP_DB:
                j += 1
            if (j - i) * step >= GAP_MIN and j < n:
                k = j
                while k < n and db[k] > GAP_DB and per[k] < PER_THR:
                    k += 1
                leng = (k - j) * step
                if leng >= NOI_MIN:
                    lv = db[j:k]
                    art = max(art, round(leng, 3))
                    kind = "zeros" if zeros > 0 else "dip"
                    i = max(k, i + 1)
                    continue
            i = j
            continue
        i += 1
    return {"dur": round(dur, 2), "tail_art": art, "kind": kind,
            "zeros": zeros, "last_voiced": round(last * step, 3)}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "_audio_ch123/out"
    out = sys.argv[2] if len(sys.argv) > 2 else "_scan_tail2.json"
    files = sorted(glob.glob(os.path.join(d, "*.wav")))
    res = {}
    for k, f in enumerate(files):
        rid = os.path.basename(f)[:-4]
        try:
            res[rid] = analyze(f)
        except Exception as e:
            res[rid] = {"err": str(e), "tail_art": 0.0, "kind": "err"}
        if (k + 1) % 200 == 0:
            print("  %d/%d" % (k + 1, len(files)))
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    hit = {k: v for k, v in res.items() if v.get("tail_art", 0) >= NOI_MIN}
    z = sum(1 for v in hit.values() if v.get("kind") == "zeros")
    print("\n扫描 %d 条" % len(res))
    print("  假尾命中 %d 条（其中带数字零 %d / 仅电平掉落 %d）" % (len(hit), z, len(hit) - z))
    print("  伪噪总时长 %.2fs" % sum(v["tail_art"] for v in hit.values()))
    order = sorted(hit, key=lambda k: -hit[k]["tail_art"])
    print("\n  最长的 20 条：")
    for k in order[:20]:
        v = hit[k]
        print("    %-9s 假尾 %.3fs  %-5s  dur %.2fs  末浊音 %.2fs" %
              (k, v["tail_art"], v["kind"], v["dur"], v["last_voiced"]))
    json.dump(sorted(hit), open("_scan_tail2_ids.json", "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
