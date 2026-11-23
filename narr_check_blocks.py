# -*- coding: utf-8 -*-
"""旁白 chunk 产物的验收：按句切开测，不整块测。

为什么必须切开
--------------
2026-11-11 实测：B000 是 66 秒的 chunk，整块测 energy_span = 5.6（判 LOW，看着像废案）；
按 cut_units 切回 21 句后，可测句的 span 中位 = 19.3 —— 与旧链路 716 条的 19.2 一致。

原因是 energy_span 量的是「能量轮廓的高低差」，长音频里几十个句子的能量被抹平在同一
个平台上，跨度自然缩小。`_rhythm_bands.json` 的标定样本是句级（2–20 秒），所以整块测
属于超范围使用，结论不可比。

本脚本输出两级结果：
  1. 块级（只报，不判）—— 留档，用于看这个块整体有没有异常
  2. 句级（用于判定）—— 与旧链路同口径，可直接和 716 条对比
"""
import argparse
import json
import os
import statistics
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import narr_check as NC

MIN_DUR = 2.5   # 与 narr_check.ENERGY_MIN_DUR 一致：短于此 span 不外推


def analyze_file(p):
    y, sr = sf.read(p)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y, dtype=np.float32)
    whole = NC.l1_unit(y, sr)
    units = NC.cut_units(y, sr)
    sents = []
    for a, b in units:
        seg = y[int(a * sr):int(b * sr)]
        d = NC.l1_unit(seg, sr)
        d["t0"], d["t1"] = round(a, 2), round(b, 2)
        d["dur"] = round(len(seg) / sr, 2)
        sents.append(d)
    return whole, sents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="G:/_setup/_narr_new/out")
    ap.add_argument("--out", default="G:/_setup/_narr_block_check.json")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.dir) if f.endswith(".wav"))
    if a.limit:
        files = files[:a.limit]
    print("待检 %d 个块" % len(files), flush=True)

    rows = []
    for k, fn in enumerate(files, 1):
        p = os.path.join(a.dir, fn)
        try:
            whole, sents = analyze_file(p)
        except Exception as e:
            print("[%d/%d] %s ERR %s" % (k, len(files), fn, e), flush=True)
            continue
        meas = [s for s in sents if s["dur"] >= MIN_DUR and s["energy_span"] is not None]
        spans = sorted(s["energy_span"] for s in meas)
        rec = {
            "block": fn[:-4],
            "block_dur": whole.get("dur"),
            "block_span": whole.get("energy_span"),
            "block_band": whole.get("energy_band"),
            "n_sent": len(sents),
            "n_meas": len(meas),
            "sent_span_p10": spans[int(0.1 * len(spans))] if spans else None,
            "sent_span_med": statistics.median(spans) if spans else None,
            "sent_span_max": spans[-1] if spans else None,
            "fix_sents": [{"t0": s["t0"], "why": s.get("why")}
                          for s in sents if s.get("verdict") == "FIX"],
            "f0_med": whole.get("f0_med"),
            "sents": [{kk: s.get(kk) for kk in
                       ("t0", "t1", "dur", "verdict", "energy_span", "energy_band",
                        "f0_med", "f0_jump_n", "cut_hard", "hnr_med", "why")}
                      for s in sents],
        }
        rows.append(rec)
        print("[%d/%d] %s 块 %.1fs span=%s band=%s | 句 n=%d 可测=%d 中位=%s"
              % (k, len(files), rec["block"], rec["block_dur"] or 0,
                 rec["block_span"], rec["block_band"], rec["n_sent"], rec["n_meas"],
                 rec["sent_span_med"]), flush=True)

    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写 %s" % a.out)

    allspan = sorted(s["energy_span"] for r in rows for s in r["sents"]
                     if s["dur"] and s["dur"] >= MIN_DUR and s.get("energy_span") is not None)
    if allspan:
        print("句级汇总（%d 句）: p10=%.1f 中位=%.1f p90=%.1f"
              % (len(allspan), allspan[int(0.1 * len(allspan))],
                 statistics.median(allspan), allspan[int(0.9 * len(allspan))]))
        print("对照：真人切片 p10=29.2 / 中位=37.0；旧链路 716 条 p10=12.9 / 中位=19.2")


if __name__ == "__main__":
    main()
