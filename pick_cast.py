# -*- coding: utf-8 -*-
"""从一个聚类簇里挑可用参考句：技术指标 + 串音检测 + 韵律指标排序。

串音检测是这里最要紧的一步。能量切句会把「两个人挨着说话」切进同一段，
这种段拿去做参考音，声纹会被对方污染 —— 城堡那次就是 1−A 被静音刷分、
指标最高那条其实不是该角色说的。做法：段向量到本簇质心的余弦要高，
到其它簇质心的余弦要低，差值就是纯度分。

用法:
  python pick_cast.py --seg out/hope_full/segments.json --cl 2 --out out/hope_edward.json
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")


def f0_stats(x, sr):
    import parselmouth as pm
    if len(x) < sr * 0.3:
        return 0.0, 0.0
    snd = pm.Sound(x.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f = pit.selected_array["frequency"]
    f = f[f > 0]
    if not len(f):
        return 0.0, 0.0
    return float(np.median(f)), float(np.std(f))


def voiced_ratio(x, sr, thr_db=-45.0):
    w = int(0.01 * sr)
    n = len(x) // w
    if n < 1:
        return 0.0
    fr = x[: n * w].reshape(n, w)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    return float((db > thr_db).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seg", required=True)
    ap.add_argument("--cl", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-dur", type=float, default=2.0)
    ap.add_argument("--max-dur", type=float, default=8.5)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()

    d = json.load(open(a.seg, encoding="utf-8"))
    rows = d["rows"]
    from chain_check import EmoVoice
    ev = EmoVoice()

    # 先算各簇质心
    cents = {}
    for c in sorted(set(r["cl"] for r in rows)):
        E = np.array([ev.m.embed(r["path"]) for r in rows if r["cl"] == c], dtype=np.float32)
        v = E.mean(axis=0)
        cents[c] = v / (np.linalg.norm(v) + 1e-9)

    pool = [r for r in rows if r["cl"] == a.cl
            and a.min_dur <= r["dur"] <= a.max_dur]
    print("簇 %d 候选 %d 条（%0.1f–%0.1fs）" % (a.cl, len(pool), a.min_dur, a.max_dur), flush=True)

    out = []
    for i, r in enumerate(pool, 1):
        x, sr = sf.read(r["path"], dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        e = ev.m.embed(r["path"])
        own = float(e @ cents[a.cl])
        other = max(float(e @ v) for c, v in cents.items() if c != a.cl)
        f0, sd = f0_stats(x, sr)
        vr = voiced_ratio(x, sr)
        head = float(20 * np.log10(np.sqrt((x[: int(0.05 * sr)] ** 2).mean()) + 1e-9))
        tail = float(20 * np.log10(np.sqrt((x[-int(0.05 * sr):] ** 2).mean()) + 1e-9))
        body = float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))
        out.append({
            "path": r["path"], "t0": r["t0"], "dur": round(r["dur"], 2),
            "f0": round(f0, 1), "f0_sd": round(sd, 1), "voiced": round(vr, 3),
            "pure": round(own - other, 3), "own": round(own, 3),
            "head_drop": round(head - body, 1), "tail_drop": round(tail - body, 1),
            "body_db": round(body, 1),
        })
        if i % 40 == 0:
            print("  评 %d/%d" % (i, len(pool)), flush=True)

    ok = [c for c in out
          if c["pure"] >= 0.12 and c["voiced"] >= 0.55
          and c["tail_drop"] > -35 and c["head_drop"] > -35]
    ok.sort(key=lambda c: -c["pure"])
    print("\n过硬检查 %d / %d 条" % (len(ok), len(out)))

    print("\n%-4s %7s %4s %4s %5s %6s %6s %s" % ("i", "t0", "dur", "f0", "sd", "pure", "尾巴", "文件"))
    for i, c in enumerate(ok[: a.top], 1):
        print("%-4d %7.1f %4.1f %4.0f %5.1f %6.2f %6.0f %s" % (
            i, c["t0"], c["dur"], c["f0"], c["f0_sd"], c["pure"], c["tail_drop"],
            os.path.basename(c["path"])))

    json.dump(ok, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 -> %s（%d 条）" % (a.out, len(ok)))


if __name__ == "__main__":
    main()
