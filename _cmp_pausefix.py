# -*- coding: utf-8 -*-
"""比较两次停顿注入（whisper 词时间 vs 字符级强制对齐词时间）的结果。"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def load(fn):
    p = os.path.join(HERE, fn)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def summarize(tag, R):
    if not R:
        print(tag, "缺失")
        return
    add = np.array([r.get("add", 0) for r in R], float)
    filled = np.array([r.get("filled", 0) for r in R], int)
    trims = [t for r in R for t in (r.get("trims") or [])]
    skips = [s for r in R for s in (r.get("skipped") or [])]
    sw = [s for r in R for s in (r.get("expr_swallow") or [])]
    dur = np.array([r["dur"] for r in R]); od = np.array([r["out_dur"] for r in R])
    ratio = od / dur
    print("== %s  n=%d" % (tag, len(R)))
    print("   插入 %d 处 / %d 句；跳过 %d 处；压缩 %d 处；吞字 %d 处 / %d 句"
          % (filled.sum(), int((filled > 0).sum()), len(skips), len(trims),
             len(sw), len(set((s.get("k") or s.get("sid") or "") for s in sw))))
    print("   总补时 %+.1fs   总时长 %.0f→%.0f s (%+.1f%%)"
          % (add.sum(), dur.sum(), od.sum(), (od.sum() / dur.sum() - 1) * 100))
    print("   逐句时长比 中位 %+.1f%%  p10 %+.1f%%  p90 %+.1f%%"
          % ((np.median(ratio) - 1) * 100, (np.percentile(ratio, 10) - 1) * 100,
             (np.percentile(ratio, 90) - 1) * 100))
    print("   变长>2%% %d / 变短>2%% %d" % (int((ratio > 1.02).sum()), int((ratio < 0.98).sum())))
    d = [t["d"] for t in trims]
    if d:
        print("   压缩步长 p10/50/90 = %.2f/%.2f/%.2f s"
              % (np.percentile(d, 10), np.median(d), np.percentile(d, 90)))
    ins = [b for r in R for b in (r.get("bounds") or [])
           if b.get("op") == "ins" and b.get("after") is not None and b.get("tgt") is not None]
    if ins:
        err = np.array([abs(b["after"] - b["tgt"]) for b in ins])
        print("   插入后 |after−tgt| p50 %.3f  p90 %.3f  ≤0.15 占比 %.0f%%"
              % (np.median(err), np.percentile(err, 90), np.mean(err <= 0.15) * 100))
    print()


if __name__ == "__main__":
    summarize("whisper 词时间", load("_pause_fix_report.json"))
    summarize("强制对齐词时间", load("_pause_fix2_report.json"))
