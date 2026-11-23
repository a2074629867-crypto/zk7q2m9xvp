# -*- coding: utf-8 -*-
"""起伏闸门 _gate_contour.py —— 按马修母带标定的句内 F0 起伏判据。

    python _gate_contour.py --dir _mt_raw_s42 --json _gate_contour_s42.json
    python _gate_contour.py --dir _mt_raw_s42 --ref _mt_raw_s2024 --deadzone
    python _gate_contour.py --wav N0004.wav

判据只有一个：**段级 IQR 中位数**（p75−p25，单位半音）。

为什么不是 p95−p5：那个量被 1~2 个倍频/突变帧拉爆。N0002 raw 13.92 而 IQR 2.55
（倍频帧仅 1/57）；p95−p5 跨文件 6.7 倍、IQR 只跨 3 倍。见 skill 18.35。

马修母带标定（627 段，parselmouth ac floor60/ceil250/vt0.20）：
    p10 1.10 / p25 1.44 / p50 1.94 / p75 2.77 / p90 4.18
    按段长分层 1.93/1.97/1.93/2.03 —— 不随段长变，是硬常量。
我们生成（_mt_raw_s42, 2212 段）：
    p10 1.83 / p25 2.43 / p50 3.54 / p75 5.06 / p90 6.91  ⇒ 比值 1.82

三档输出：
    OK     1.10 ~ 4.18（马修 p10~p90），可直接用
    HIGH   > 4.18，起伏过多，需换候选
    LOW    < 1.10，起伏不足（几乎不出，我们 p10 都 1.83）
    SHORT  段数 < 2 或有效 voiced 帧 < 30，无法测

★ 死区：跨 seed 的 |ΔIQR| 分布由 --deadzone 实测给出。判 HIGH/LOW 时必须
   超过死区才算数，否则等于在噪声里挑。这是第 9 次同型错误的教训。
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import numpy as np

from mt_matt_contour import segs_of, f0_track, shape_feats

# 马修母带标定（matt_contour.json，627 段）
MATT = {
    "p10": 1.10, "p25": 1.44, "p50": 1.94, "p75": 2.77, "p90": 4.18,
    "decl_p50": -1.70,
}
# 判据阈值：用 p10 / p90 做外包络（允许马修自己也会出现的范围）
LO = MATT["p10"]
HI = MATT["p90"]


def contour_of(path, min_seg=1, min_voiced=30):
    """返回单条音频的轮廓特征。失败返回 None。"""
    try:
        segs, x, sr = segs_of(path)
    except Exception:
        return None
    if not segs:
        return None
    feats = []
    n_voiced = 0
    for a, b in segs:
        tr, st = f0_track(x, sr, a, b)
        if tr is None:
            continue
        n_voiced += len(st)
        feats.append(shape_feats(tr, st))
    if len(feats) < min_seg or n_voiced < min_voiced:
        return None
    iqr = float(np.median([f["iqr_st"] for f in feats]))
    return {
        "iqr": round(iqr, 3),
        "span": round(float(np.median([f["span_st"] for f in feats])), 3),
        "decl": round(float(np.median([f["decl_st"] for f in feats])), 3),
        "n_peaks": round(float(np.median([f["n_peaks"] for f in feats])), 2),
        "n_seg": len(feats),
        "n_voiced": n_voiced,
        "flat_pct": round(float(np.mean([f["shape"] == "flat" for f in feats])), 3),
        "shape": _mode([f["shape"] for f in feats]),
    }


def _mode(xs):
    from collections import Counter
    return Counter(xs).most_common(1)[0][0] if xs else None


def verdict(rec, deadzone=0.0):
    """三档判定。deadzone 由跨 seed 实测给出，避免在噪声里挑。"""
    if rec is None:
        return "SHORT"
    v = rec["iqr"]
    if v > HI + deadzone:
        return "HIGH"
    if v < LO - deadzone:
        return "LOW"
    return "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    ap.add_argument("--wav")
    ap.add_argument("--json")
    ap.add_argument("--ref", help="对照目录，用于算跨 seed 死区")
    ap.add_argument("--deadzone", action="store_true", help="只算死区")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if a.wav:
        r = contour_of(a.wav)
        print(json.dumps(r, ensure_ascii=False, indent=1) if r else "FAIL")
        return

    if not a.dir:
        ap.error("需要 --dir 或 --wav")

    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    if a.limit:
        files = files[:a.limit]
    rows = {}
    for i, f in enumerate(files):
        n = os.path.splitext(os.path.basename(f))[0]
        r = contour_of(f)
        if r:
            r["verdict"] = verdict(r)
        rows[n] = r
        if (i + 1) % 100 == 0:
            print("  %d / %d" % (i + 1, len(files)), flush=True)

    ok = [r for r in rows.values() if r]
    print("\n=== %s  n=%d / %d ===" % (os.path.basename(a.dir), len(ok), len(files)))
    if not ok:
        return
    iq = np.array([r["iqr"] for r in ok])
    print("  IQR  p10 %.2f  p25 %.2f  p50 %.2f  p75 %.2f  p90 %.2f  mean %.2f"
          % tuple(list(np.percentile(iq, [10, 25, 50, 75, 90])) + [iq.mean()]))
    print("  马修 p10 %.2f  p25 %.2f  p50 %.2f  p75 %.2f  p90 %.2f"
          % (MATT["p10"], MATT["p25"], MATT["p50"], MATT["p75"], MATT["p90"]))
    print("  比值 p50 %.2f" % (np.median(iq) / MATT["p50"]))
    from collections import Counter
    c = Counter(r["verdict"] for r in ok)
    tot = len(ok)
    print("  判定  " + "  ".join("%s %d(%.0f%%)" % (k, v, 100 * v / tot)
                                 for k, v in sorted(c.items())))
    fl = np.array([r["flat_pct"] for r in ok])
    print("  flat 段占比 中位 %.1f%%（马修 14%%）" % (100 * np.median(fl)))

    out = {"dir": a.dir, "n": len(ok), "matt": MATT,
           "dist": {k: round(float(np.percentile(iq, q)), 3)
                    for k, q in [("p10", 10), ("p25", 25), ("p50", 50),
                                 ("p75", 75), ("p90", 90)]},
           "verdicts": dict(c), "rows": rows}

    # 跨 seed 死区
    if a.ref and os.path.isdir(a.ref):
        pairs = []
        for n, r in rows.items():
            p2 = os.path.join(a.ref, n + ".wav")
            if not r or not os.path.exists(p2):
                continue
            r2 = contour_of(p2)
            if not r2:
                continue
            pairs.append((n, r["iqr"], r2["iqr"]))
        if pairs:
            A = np.array([[p[1], p[2]] for p in pairs])
            d = A[:, 1] - A[:, 0]
            out["deadzone"] = {
                "n": len(pairs),
                "abs_delta_p50": round(float(np.median(abs(d))), 3),
                "abs_delta_p75": round(float(np.percentile(abs(d), 75)), 3),
                "abs_delta_p90": round(float(np.percentile(abs(d), 90)), 3),
                "delta_p50": round(float(np.median(d)), 3),
                "min_of_2_p50": round(float(np.median(A.min(1))), 3),
                "hit_lt_p75": {"single": round(float((A[:, 0] <= MATT["p75"]).mean()), 3),
                               "min2": round(float((A.min(1) <= MATT["p75"]).mean()), 3)},
            }
            print("\n=== 跨 seed 死区（n=%d）===" % len(pairs))
            print("  |ΔIQR| p50 %.2f  p75 %.2f  p90 %.2f"
                  % (out["deadzone"]["abs_delta_p50"],
                     out["deadzone"]["abs_delta_p75"],
                     out["deadzone"]["abs_delta_p90"]))
            print("  Δ 中位 %+.2f（应接近 0，否则有系统性偏移）"
                  % out["deadzone"]["delta_p50"])
            print("  ≤马修p75 命中率：单候选 %.0f%% → 两候选取最小 %.0f%%"
                  % (100 * out["deadzone"]["hit_lt_p75"]["single"],
                     100 * out["deadzone"]["hit_lt_p75"]["min2"]))

    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n  → %s" % a.json)


if __name__ == "__main__":
    main()
