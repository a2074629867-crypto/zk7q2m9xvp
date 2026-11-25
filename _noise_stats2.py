# -*- coding: utf-8 -*-
"""_noise_stats2.py —— 底噪双口径统计（修正 p10 系统性偏差）。

为什么要有 v2（2026-11-24 实测）：
  旧口径 `floor = p10`（_noise_stats.py / _ref_audit.py）在**语音密度高**的条目上
  会系统性报高 —— 因为 10% 分位的帧还落在语音尾音里，不是真静音。
  证据：_refs_v3 的 8 条「底噪 > −60」实测 p1 全在 −67 ~ −76，voiced 占比 0.56~0.71；
  同为参考的 Thomas_calm（voiced 0.40）p10 −65.3 ≈ p1 −66.6，两者才一致。

新口径（三个都算，判断用静音帧口径）：
  floor_p10 : 旧口径，保留只为对比
  floor_p1  : 1% 分位（极端静音）
  floor_q   : **静音帧中位数** —— 帧能量 < p95 − 35dB 的帧（人声以下 35dB 不可能是语音）
  snr_q     : p95 − floor_q
  dense     : 静音帧占比（< 0.05 时静音口径不可靠，标记）
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def stats(p):
    x, sr = sf.read(p, dtype="float64")
    if x.ndim > 1:
        x = x.mean(1)
    w = int(0.01 * sr)
    n = len(x) // w
    fr = np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(fr)
    p95 = float(np.percentile(db, 97))

    z = np.flatnonzero(x == 0.0)
    zero_ms = 0.0
    if len(z):
        runs = np.split(z, np.flatnonzero(np.diff(z) != 1) + 1)
        zero_ms = sum(len(r) / sr * 1000 for r in runs if len(r) / sr >= 0.010)

    q = db[db < p95 - 35.0]
    floor_q = float(np.median(q)) if len(q) >= 20 else float(np.percentile(db, 1))
    return dict(dur=round(len(x) / sr, 2),
                floor_p10=round(float(np.percentile(db, 10)), 1),
                floor_p1=round(float(np.percentile(db, 1)), 1),
                floor_q=round(floor_q, 1),
                snr_q=round(p95 - floor_q, 1),
                dense=round(len(q) / len(db), 3),
                zero_ms=round(zero_ms, 1),
                peak=round(float(np.abs(x).max()), 3))


def batch(paths, tag):
    rows = {}
    for p in paths:
        k = os.path.basename(p)[:-4]
        try:
            rows[k] = stats(p)
        except Exception as e:
            rows[k] = {"err": "%s:%s" % (type(e).__name__, e)}
    good = [v for v in rows.values() if "floor_q" in v]
    if good:
        for key in ("floor_p10", "floor_p1", "floor_q", "snr_q"):
            v = [x[key] for x in good]
            print("%-10s %-10s min %7.1f  p50 %7.1f  max %7.1f  跨度 %5.1f"
                  % (tag, key, min(v), np.median(v), max(v), max(v) - min(v)))
        print("%-10s 静音帧占比 dense: min %.3f  p50 %.3f  (低 <0.05 说明几乎无静音)"
              % (tag, min(x["dense"] for x in good),
                 np.median([x["dense"] for x in good])))
        print("%-10s zero_ms>10 的: %d / %d"
              % (tag, sum(1 for x in good if x["zero_ms"] > 10), len(good)))
    return rows


def main():
    out = {}
    refs = sorted(glob.glob("G:/_setup/_refs_v3/*.wav"))
    print("===== 参考库 _refs_v3 (%d 条) =====" % len(refs))
    out["refs_v3"] = batch(refs, "refs_v3")

    ids = [r["id"] for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))]
    paths = ["G:/_setup/_audio_ch123/out/%s.wav" % i for i in ids]
    paths = [p for p in paths if os.path.exists(p)]
    print("\n===== 成品 out (%d 条) =====" % len(paths))
    out["dlg_out"] = batch(paths, "dlg")

    json.dump(out, open("G:/_setup/_noise_stats2.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("-> _noise_stats2.json")


if __name__ == "__main__":
    main()
