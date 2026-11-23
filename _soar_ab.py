# -*- coding: utf-8 -*-
"""_soar_ab.py —— 云端 SOAR bf16 与本地 Edit q8_0 的同 seed 对照。

两边同文本、同 seed、同参考音频，差异只在「变体 + 精度」（两个变量同时变，
所以只能说整体差异，不能归因到某一个变量）。

口径全部沿用已验证的那套：
  voiced wpm  = 词数 / voiced 时长（只算发声帧，剔除内部停顿）
  span wpm    = 词数 / 首尾 voiced 帧跨度
  语音段数     = VAD 段计数
  F0 IQR      = voiced 帧半音 IQR（单条无判别力，只报批次中位）
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf
import mt_final_pause as FP


def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))


def measure(path, w):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(1)
    db, n, hop = FP.frame_db(x, sr)
    if len(db) == 0:
        return None
    on = db > (np.percentile(db, 90) - 25.0)
    idx = np.where(on)[0]
    if len(idx) < 5:
        return None
    v = float(len(idx)) * hop / sr
    span = float(idx[-1] - idx[0] + 1) * hop / sr
    gaps = np.diff(idx)
    nseg = 1 + int((gaps > int(0.05 / 0.01)).sum())
    return dict(dur=len(x) / sr, voiced=v, span=span, nseg=nseg,
                v_wpm=w / v * 60 if v > 0.05 else np.nan,
                s_wpm=w / span * 60 if span > 0.05 else np.nan,
                peak=float(np.abs(x).max()))


def batch(dirs, S, tag, ch="ch1"):
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
            uid = os.path.basename(p)[:-4]
            if uid not in S or (ch and S[uid].get("ch") != ch):
                continue
            m = measure(p, nwords(S[uid]["text"]))
            if m:
                m["uid"] = uid
                m["dir"] = d
                rows.append(m)
    if not rows:
        print("%-22s 无数据" % tag)
        return []
    a = lambda k: np.array([r[k] for r in rows if np.isfinite(r[k])])
    print("%-22s n=%3d  时长 p50 %5.2f  voiced %5.2f  段数 %4.1f  "
          "v_wpm %3.0f/%3.0f/%3.0f  s_wpm %3.0f/%3.0f/%3.0f  峰值 %.2f"
          % (tag, len(rows),
             np.median(a("dur")), np.median(a("voiced")), np.mean(a("nseg")),
             np.percentile(a("v_wpm"), 10), np.median(a("v_wpm")), np.percentile(a("v_wpm"), 90),
             np.percentile(a("s_wpm"), 10), np.median(a("s_wpm")), np.percentile(a("s_wpm"), 90),
             a("peak").max()))
    return rows


def pair(rows_a, rows_b, ka, kb):
    """同 uid 配对比较，返回比值数组。"""
    da = {r["uid"]: r for r in rows_a}
    db = {r["uid"]: r for r in rows_b}
    common = sorted(set(da) & set(db))
    out = {}
    for k in ka:
        v = []
        for u in common:
            x, y = da[u][k], db[u][k]
            if np.isfinite(x) and np.isfinite(y) and min(x, y) > 1e-6:
                v.append(max(x, y) / min(x, y))
        out[k] = np.array(v)
    return common, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="G:/_setup/_mt_loop_state.json")
    ap.add_argument("--a", default="_mt_raw_s42,_mt_raw_s1234", help="旧（本地 Edit q8_0）")
    ap.add_argument("--b", default="_mt_raw_ch1_s42,_mt_raw_ch1_s1234", help="新（云端 SOAR bf16）")
    ap.add_argument("--json", default="_soar_ab.json")
    a = ap.parse_args()

    S = json.load(open(a.state, encoding="utf-8"))["units"]
    da = [d for d in a.a.split(",") if os.path.isdir(d)]
    db = [d for d in a.b.split(",") if os.path.isdir(d)]
    print("旧:", da)
    print("新:", db)
    print()
    A = batch(da, S, "旧 Edit q8_0")
    B = batch(db, S, "新 SOAR bf16")
    print()

    if A and B:
        common, r = pair(A, B, ["dur", "voiced", "v_wpm", "s_wpm", "nseg"], [])
        print("同 uid 配对 n=%d（同文本同 seed，只有变体+精度不同）\n" % len(common))
        print("%-10s %7s %7s %7s %7s" % ("指标", "p50", "p75", "p90", "max"))
        for k, tag in (("dur", "总时长比"), ("voiced", "voiced 比"),
                       ("v_wpm", "voiced wpm 比"), ("s_wpm", "span wpm 比"),
                       ("nseg", "段数比")):
            v = r[k]
            if not len(v):
                continue
            print("%-10s %7.2f %7.2f %7.2f %7.2f" % (tag, np.median(v),
                  np.percentile(v, 75), np.percentile(v, 90), v.max()))
        # 段数完全相同的比例
        da_ = {x["uid"]: x for x in A}
        db_ = {x["uid"]: x for x in B}
        same = sum(1 for u in common if da_[u]["nseg"] == db_[u]["nseg"])
        print("\n段数完全相同 %d / %d (%.0f%%)" % (same, len(common), 100 * same / len(common)))
        json.dump(dict(common=len(common),
                       ratios={k: dict(p50=float(np.median(v)),
                                        p90=float(np.percentile(v, 90)),
                                        max=float(v.max()))
                               for k, v in r.items() if len(v)}),
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写", a.json)


if __name__ == "__main__":
    main()
