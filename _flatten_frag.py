# -*- coding: utf-8 -*-
"""_flatten_frag.py —— 把「洞—短残音—洞」中间那一小截压到洞内底噪（消「碎」）。

用户 2026-11-25 09:0x 听出「突然停了一下」，波形上就是
    洞(1.14s) + 0.06s 有声 + 洞(0.78s)
那一小截有声**不是词**（`_frag_truth.py` 用交付版自己的词时间戳验证：A+B 里
不含完整词的占绝大多数），是词尾摩擦音 / 气口残响被两段静音夹住了。

做法：不改时长、不删样本、不动词，只在那一小截上乘一条增益包络，
把它降到两侧洞内底噪的电平（首尾 10ms 余弦渐变，不留台阶）。
判据只看「两边都是 ≥0.15s 的洞」且「中间那一截 <0.15s」——
超过 0.15s 就是完整词，一律不碰。

用法：
  G:/Python310/python.exe -u _flatten_frag.py --in _pause_fix4 --out _fix4_flat [--dry]
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))

HOLE_MIN = 0.15        # 洞的最小长度
MID_MAX = 0.15         # 夹层最大长度（超过就是词，不碰）
SOFT_MIN = 3.0         # 夹层峰值至少要高出洞内底噪 3dB 才处理
FADE = 0.010


def runs_of(db, thr, minlen, hop_t):
    n = len(db)
    out, i = [], 0
    while i < n:
        if db[i] < thr:
            j = i
            while j < n and db[j] < thr:
                j += 1
            if (j - i) * hop_t >= minlen:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def process(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    hop = int(sr * 0.02)
    n = len(y) // hop
    if n < 20:
        return None
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    db = 20 * np.log10(e)
    thr = max(np.percentile(db, 90) - 20, -60)
    rs = runs_of(db, thr, HOLE_MIN, 0.02)
    hits = []
    for (a0, a1), (b0, b1) in zip(rs, rs[1:]):
        mid = b0 - a1
        if mid <= 0 or mid * 0.02 >= MID_MAX:
            continue
        peak = float(db[a1:b0].max())
        floor = float(np.median(np.concatenate([db[a0:a1], db[b0:b1]])))
        if peak < floor + SOFT_MIN:
            continue
        hits.append((a1, b0, peak, floor))
    if not hits:
        return None
    out = y.copy()
    nf = max(1, int(FADE * sr))
    for i0, i1, peak, floor in hits:
        g = 10 ** ((floor - peak) / 20.0)
        s, t = i0 * hop, min(i1 * hop, len(out))
        if t - s < 4:
            continue
        env = np.full(t - s, g, dtype=np.float32)
        f = min(nf, (t - s) // 2)
        if f > 0:
            env[:f] = np.linspace(1.0, g, f)
            env[-f:] = np.linspace(g, 1.0, f)
        out[s:t] *= env
    return out, sr, len(hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    src = os.path.join(HERE, a.inp)
    dst = os.path.join(HERE, a.out)
    if not a.dry:
        os.makedirs(dst, exist_ok=True)
    ids = set(json.load(open(os.path.join(HERE, "_narr_ids716.json"), encoding="utf-8")))
    files, fixed, tot = 0, 0, 0
    rep = []
    for p in sorted(glob.glob(src + "/*.wav")):
        sid = os.path.basename(p)[:-4]
        if sid not in ids:
            continue
        files += 1
        r = process(p)
        if r is None:
            if not a.dry:
                sf.write(os.path.join(dst, sid + ".wav"), sf.read(p, dtype="float32")[0],
                         sf.info(p).samplerate, subtype="PCM_16")
            continue
        y2, sr, nh = r
        fixed += 1
        tot += nh
        rep.append(dict(sid=sid, n=nh))
        if not a.dry:
            sf.write(os.path.join(dst, sid + ".wav"), y2, sr, subtype="PCM_16")
    print("%s → %s：%d 条，命中 %d 条，压平 %d 处" % (a.inp, a.out, files, fixed, tot))
    if a.report:
        json.dump(rep, open(os.path.join(HERE, a.report), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("→", a.report)


if __name__ == "__main__":
    main()
