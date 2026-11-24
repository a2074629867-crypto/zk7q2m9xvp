# -*- coding: utf-8 -*-
"""扫「数字零缺口 + 之后的无基频噪声」。

判据（严格版，误报率极低）：
1. 存在一段 >=10ms 的**逐采样精确为零**（np.abs(y)==0）的缺口 —— 人声/环境声不可能出现，
   只有模型补零才会；
2. 缺口之后紧跟 >=30ms 的 `db>-42 且 periodicity<0.35` 段；
3. 记录缺口是否在文件末尾 60ms 内（尾噪），否则算句中伪影。
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

Z_MIN = 0.010
NOI_DB = -42.0
NOI_MIN = 0.030
PER_THR = 0.35


def zero_runs(y, sr):
    z = np.where(np.abs(y) == 0)[0]
    if not len(z):
        return []
    out = []
    for s in np.split(z, np.where(np.diff(z) > 1)[0] + 1):
        if len(s) >= sr * Z_MIN:
            out.append((s[0], s[-1] + 1))
    return out


def periodicity(y, sr, i0, i1):
    """[i0,i1) 内的平均 periodicity（25ms 窗，10ms 步）"""
    w, h = int(0.025 * sr), int(0.010 * sr)
    a, b = int(sr / 400), int(sr / 60)
    vals = []
    for i in range(i0, max(i0 + 1, i1 - w), h):
        fr = y[i:i + w]
        if len(fr) < w or np.sqrt((fr ** 2).mean()) < 10 ** (NOI_DB / 20):
            continue
        f = fr - fr.mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        if b < len(ac):
            vals.append(ac[int(np.argmax(ac[a:b])) + a] / (ac[0] + 1e-12))
    return float(np.mean(vals)) if vals else 0.0


def analyze(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    hits = []
    for a, b in zero_runs(y, sr):
        # 缺口之后的噪声段：连续满足 电平>NOI_DB 且 无基频
        w, h = int(0.025 * sr), int(0.010 * sr)
        i = b
        end = b
        aa, bb = int(sr / 400), int(sr / 60)
        while i + w < len(y):
            fr = y[i:i + w]
            if np.sqrt((fr ** 2).mean()) < 10 ** (NOI_DB / 20):
                break
            f = fr - fr.mean()
            ac = np.correlate(f, f, "full")[w - 1:]
            if bb >= len(ac):
                break
            per = ac[int(np.argmax(ac[aa:bb])) + aa] / (ac[0] + 1e-12)
            if per >= PER_THR:
                break
            end = i + w
            i += h
        leng = (end - b) / sr
        if leng >= NOI_MIN:
            hits.append({"zero": [round(a / sr, 3), round(b / sr, 3)],
                         "zero_s": round((b - a) / sr, 3),
                         "noise_s": round(leng, 3),
                         "per": round(periodicity(y, sr, b, end), 3),
                         "at_end": bool(dur - end / sr < 0.060)})
    return {"dur": round(dur, 2), "hits": hits, "n": len(hits),
            "tail": any(x["at_end"] for x in hits)}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "_audio_ch123/out"
    out = sys.argv[2] if len(sys.argv) > 2 else "_scan_falsetail2.json"
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
    tail = sorted(k for k, v in hit.items() if v.get("tail"))
    mid = sorted(k for k, v in hit.items() if not v.get("tail"))
    print("\n扫描 %d 条" % len(res))
    print("  命中（零缺口+无基频噪声）：%d 条" % len(hit))
    print("    · 文件末尾伪噪：%d 条" % len(tail))
    print("    · 仅句中伪影  ：%d 条" % len(mid))
    print("  伪噪总时长 %.2fs" % sum(h["noise_s"] for v in hit.values() for h in v["hits"]))
    order = sorted(tail, key=lambda k: -max(h["noise_s"] for h in res[k]["hits"]))
    print("\n  末尾伪噪最长 12 条：")
    for k in order[:12]:
        h = max(res[k]["hits"], key=lambda x: x["noise_s"])
        print("    %-9s 零 %.3fs + 噪 %.3fs  per %.2f  (dur %.2fs)" %
              (k, h["zero_s"], h["noise_s"], h["per"], res[k]["dur"]))
    json.dump({"tail": tail, "mid": mid}, open("_scan_falsetail2_hit.json", "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
