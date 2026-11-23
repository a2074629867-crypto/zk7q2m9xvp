# -*- coding: utf-8 -*-
"""给已有音频造词内音高轮廓（只改 F0，不改时长/音色）。

两条动作：
  1. 目标词（副词/重读词）：造 L+H* 型轮廓 —— 词首压低，中后部冲高，尾部回落
  2. 非目标词：向词内中位收缩（压平背景）

用法：
  python _proso_shape.py --tid <tid> --sag 2 --rise 4 --peak 0.62 --flat 0.35
"""
import argparse
import json
import os
import sys

import numpy as np
import parselmouth
from parselmouth.praat import call

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(ROOT, "_align_dataset.json")

F0_LO, F0_HI = 60, 250
VT = 0.20


def load_rec(tid):
    d = json.load(open(DATASET, encoding="utf-8"))
    for r in d["records"]:
        if r.get("tid") == tid:
            return r
    raise SystemExit("找不到 tid: %s" % tid)


def hz(f, st):
    return f * (2.0 ** (st / 12.0))


def target_curve(t, t0, t1, base, sag, rise, peak, flat):
    """返回 t0..t1 内每个时刻的目标频率。sag/rise 为半音，peak 为峰位置(0..1)。"""
    u = np.clip((t - t0) / max(1e-6, t1 - t0), 0, 1)
    out = np.empty_like(u)
    for i, x in enumerate(u):
        if x <= peak:
            # 词首从 base-sag 平滑升到 base+rise
            k = x / max(1e-6, peak)
            k = k * k * (3 - 2 * k)          # smoothstep，避免折线听感
            out[i] = base * 2 ** (((-sag) + (rise + sag) * k) / 12.0)
        else:
            # 尾部从 base+rise 回落到 base+0.2*rise
            k = (x - peak) / max(1e-6, 1 - peak)
            k = k * k * (3 - 2 * k)
            out[i] = base * 2 ** ((rise - rise * 0.8 * k) / 12.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tid", required=True)
    ap.add_argument("--sag", type=float, default=2.0, help="词首压低多少半音")
    ap.add_argument("--rise", type=float, default=4.0, help="峰值抬高多少半音")
    ap.add_argument("--peak", type=float, default=0.62, help="峰在词内的相对位置")
    ap.add_argument("--flat", type=float, default=0.35, help="非目标词保留多少原有起伏(1=不动)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rec = load_rec(a.tid)
    wav = os.path.join(ROOT, rec["wav"])
    if not os.path.exists(wav):
        raise SystemExit("缺 wav: %s" % wav)

    adv = rec.get("adv")
    words = [(w["key"], float(w["t0"]), float(w["t1"]))
             for w in rec["words"] if w.get("t0") is not None and w.get("t1") is not None]

    snd = parselmouth.Sound(wav)
    man = call(snd, "To Manipulation", 0.01, F0_LO, F0_HI)
    tier = call(man, "Extract pitch tier")

    n = call(tier, "Get number of points")
    pts = []
    for i in range(1, n + 1):
        t = call(tier, "Get time from index", i)
        f = call(tier, "Get value at index", i)
        if f and f > 0:
            pts.append((t, f))
    if len(pts) < 10:
        raise SystemExit("有效 F0 点太少：%d" % len(pts))

    ts = np.array([p[0] for p in pts])
    fs = np.array([p[1] for p in pts])

    # 每个词的中位 F0 作为基线
    spans = []
    for key, t0, t1 in words:
        m = (ts >= t0) & (ts < t1)
        if m.sum() < 2:
            continue
        base = float(np.median(fs[m]))
        spans.append((key, t0, t1, base, bool(adv) and key == adv))

    newf = fs.copy()
    n_adv = 0
    for key, t0, t1, base, is_adv in spans:
        m = (ts >= t0) & (ts < t1)
        if not m.any():
            continue
        if is_adv:
            newf[m] = target_curve(ts[m], t0, t1, base, a.sag, a.rise, a.peak, a.flat)
            n_adv += 1
        else:
            newf[m] = base + (fs[m] - base) * a.flat

    # 保护：不许超出音域，也不许单点跳变过大
    newf = np.clip(newf, F0_LO * 1.02, F0_HI * 0.98)
    for i in range(1, len(newf)):
        if abs(12 * np.log2(newf[i] / newf[i - 1])) > 3.0:
            newf[i] = newf[i - 1]

    tgt = call("Create PitchTier", "target", 0.0, snd.duration)
    for t, f in zip(ts, newf):
        call(tgt, "Add point", float(t), float(f))
    call([man, tgt], "Replace pitch tier")
    res = call(man, "Get resynthesis (overlap-add)")

    out = a.out or os.path.join(ROOT, "_shape_out", a.tid.replace(":", "_").replace("|", "_") + "_shaped.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    res.save(out, "WAV")

    # 自检：改写前后，副词与其他词的词内音高变化
    def word_amp(freq):
        r = []
        for key, t0, t1, base, is_adv in spans:
            m = (ts >= t0) & (ts < t1)
            v = freq[m]
            if len(v) < 2:
                continue
            r.append((key, is_adv, float(12 * np.log2(v.max() / v.min()))))
        return r

    before = word_amp(fs)
    after = word_amp(newf)
    adv_b = [x[2] for x in before if x[1]]
    oth_b = [x[2] for x in before if not x[1]]
    adv_a = [x[2] for x in after if x[1]]
    oth_a = [x[2] for x in after if not x[1]]
    print("tid      :", a.tid)
    print("adv      :", adv, " 命中 %d 个词" % n_adv)
    print("副词 音高变化  改前 %.2f -> 改后 %.2f 半音" % (np.median(adv_b) if adv_b else 0,
                                                       np.median(adv_a) if adv_a else 0))
    print("其他词 音高变化 改前 %.2f -> 改后 %.2f 半音" % (np.median(oth_b) if oth_b else 0,
                                                       np.median(oth_a) if oth_a else 0))
    print("输出     :", out)
    return out


if __name__ == "__main__":
    main()
