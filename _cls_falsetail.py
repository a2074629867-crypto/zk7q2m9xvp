# -*- coding: utf-8 -*-
import json, os
import numpy as np
import soundfile as sf

RES = json.load(open("_scan_falsetail2.json", encoding="utf-8"))
IDS = [k for k, v in RES.items() if v.get("n")]
W, H = 0.025, 0.010


def frames(y, sr):
    w, h = int(W * sr), int(H * sr)
    n = 1 + max(0, (len(y) - w)) // h
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(n)[:, None], 0, len(y) - 1)
    seg = y[idx]
    rms = np.sqrt((seg ** 2).mean(1))
    per = np.zeros(n)
    a, b = int(sr / 400), int(sr / 60)
    for i in range(n):
        if rms[i] < 0.01:
            continue
        f = seg[i] - seg[i].mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        if b < len(ac):
            per[i] = ac[int(np.argmax(ac[a:b])) + a] / (ac[0] + 1e-12)
    return rms, per, h / sr


def main():
    cls = {}
    print("%-9s %6s %-28s %-16s %s" % ("id", "dur", "零+噪区间", "之后浊音", "分类"))
    for k in sorted(IDS):
        v = RES[k]
        y, sr = sf.read("_audio_ch123/out/%s.wav" % k, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        rms, per, step = frames(y, sr)
        voiced = (per > 0.45) & (rms > 0.01)
        hh = max(v["hits"], key=lambda x: x["noise_s"])
        z0, z1 = hh["zero"]
        e = z1 + hh["noise_s"]
        i0, i1 = int((e + 0.02) / step), int(len(rms))
        aft = np.where(voiced[i0:i1])[0]
        j0, j1 = 0, int(max(1, (z0 - 0.01) / step))
        bef = np.where(voiced[j0:j1])[0]
        a_t = round((i0 + aft[0]) * step, 2) if len(aft) else None
        if a_t is None:
            c = "tail"
        elif not len(bef):
            c = "head"
        else:
            c = "mid"
        cls[k] = c
        print("%-9s %6.2f %-28s %-16s %s" %
              (k, v["dur"], "%.2f~%.2f(噪%.2f)" % (z0, e, hh["noise_s"]),
               "有@%.2f" % a_t if a_t else "无", c))
    json.dump(cls, open("_falsetail_cls.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    from collections import Counter
    print()
    print(dict(Counter(cls.values())))


if __name__ == "__main__":
    main()
