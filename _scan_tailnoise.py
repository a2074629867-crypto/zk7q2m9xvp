# -*- coding: utf-8 -*-
"""扫描成品：句尾/段内「无基频噪声段」与「数字零空洞」。

判据（都是绝对量，不用相对阈值）：
- 数字零：np.abs(y)==0 的连续段 >= 5ms
- 无基频噪声：30ms 窗，rms>0.01（−40dBFS）且归一化自相关峰值 <0.30（periodicity）
  连续 >= 40ms 判为一段噪声（人声即使轻声也 >0.35，气声/爆破在 <0.30 且通常伴随 F0 消失）
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

SR_MIN = 0.005          # 数字零最短 5ms
PER_THR = 0.30
NOISE_MIN = 0.04
RMS_MIN = 0.01


def analyze(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr

    zeros = []
    z = np.where(np.abs(y) == 0)[0]
    if len(z):
        segs = np.split(z, np.where(np.diff(z) > 1)[0] + 1)
        for s in segs:
            if len(s) >= sr * SR_MIN:
                zeros.append((round(s[0] / sr, 3), round((s[-1] + 1) / sr, 3)))

    h, w = int(0.01 * sr), int(0.03 * sr)
    flags = []
    for i in range(0, max(0, len(y) - w), h):
        fr = y[i:i + w]
        r = float(np.sqrt((fr ** 2).mean()))
        if r < RMS_MIN:
            continue
        f = fr - fr.mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        a, b = int(sr / 400), int(sr / 60)
        if b >= len(ac):
            continue
        j = int(np.argmax(ac[a:b])) + a
        per = float(ac[j] / (ac[0] + 1e-12))
        if per < PER_THR:
            flags.append(i / sr)

    runs = []
    for t in flags:
        if runs and t - runs[-1][1] <= 0.021:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    noise = [(round(a, 2), round(b + 0.03, 2)) for a, b in runs if b - a >= NOISE_MIN - 0.011]

    tail = 0.0
    for a, b in noise:
        if b >= dur - 0.06:
            tail = max(tail, round(b - a, 3))
    return {"dur": round(dur, 2), "zeros": zeros, "noise": noise,
            "tail_noise": tail, "n_noise": len(noise)}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "_audio_ch123/out"
    out = sys.argv[2] if len(sys.argv) > 2 else "_scan_tailnoise.json"
    files = sorted(glob.glob(os.path.join(d, "*.wav")))
    res = {}
    for k, f in enumerate(files):
        rid = os.path.basename(f)[:-4]
        try:
            res[rid] = analyze(f)
        except Exception as e:
            res[rid] = {"err": str(e)}
        if (k + 1) % 40 == 0:
            print("  %d/%d" % (k + 1, len(files)))
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    ok = [v for v in res.values() if "err" not in v]
    tz = [k for k, v in res.items() if v.get("zeros")]
    tn = [k for k, v in res.items() if v.get("tail_noise", 0) >= 0.04]
    both = [k for k in tn if res[k].get("zeros")]
    print("\n扫描 %d 条" % len(ok))
    print("  有数字零空洞(>=5ms)：%d 条" % len(tz))
    print("  尾部无基频噪声(>=40ms)：%d 条" % len(tn))
    print("  两者同时有：%d 条" % len(both))
    tn2 = sorted(tn, key=lambda k: -res[k]["tail_noise"])
    print("  尾噪最长的 12 条：")
    for k in tn2[:12]:
        print("    %-9s 尾噪 %.2fs  dur %.2fs  zeros %s" %
              (k, res[k]["tail_noise"], res[k]["dur"], res[k]["zeros"][:2]))
    json.dump({"tail_noise": tn, "zeros": tz}, open("_scan_tailnoise_hit.json", "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
