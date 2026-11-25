# -*- coding: utf-8 -*-
"""把教育界 Multidimensional Fluency Scale 的 B 维（Phrasing）翻成三个可算量。

量表（Zutell & Rasinski 1991）B 维 4 级，原文：
  1 单调、无边界感、逐词读
  2 频繁 2–3 词短语、切碎；improper stress and intonation that fail to mark ends of sentences and clauses
  3 run-on、句中换气、有些碎
  4 基本按从句 / 句子单位成组

翻成：
  ① 每调群词数中位 = 词数 ÷ 组数（组 = 被 ≥0.35s 的边界切开后的段）
  ② 碎停顿占比 = <0.50s 的内部边界 ÷ 全部内部边界
  ③ 与从句对齐率 —— 需要依存树，本版**未算**（诚实标注）

级别映射（阈值是**估的，未标定**，跑了全库分布再定）：
  L1  每调群词数 < 2.0
  L2  碎停顿占比 ≥ 0.50 或 每调群词数 < 3.0
  L3  碎停顿占比 0.30–0.50
  L4  其余

用法：
  G:/Python310/python.exe -u _phrasing_score.py --dir _audio_ch123/out  --wl _wl_out2.json   --out _phr_out.json
  G:/Python310/python.exe -u _phrasing_score.py --dir _regen_final     --wl _wl_final2.json --out _phr_final.json
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

ROOT = r"G:/_setup"
sys.path.insert(0, ROOT)

BOUND_MIN = 0.35     # 算「组边界」的最小停顿
SHORT_MAX = 0.50     # 算「碎停顿」的上限
PAUSE_MIN = 0.15


def gaps(y, sr, pause_min=PAUSE_MIN, drop_db=20.0, floor_db=-60.0):
    fl = int(0.02 * sr)
    if len(y) < fl * 5:
        return []
    k = 1 + (len(y) - fl) // fl
    idx = np.arange(fl)[None, :] + fl * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    db = 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12)
    thr = max(floor_db, float(np.percentile(db, 90)) - drop_db)
    low = db < thr
    hop = fl / float(sr)
    runs, i, n = [], 0, len(low)
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    dur = len(y) / float(sr)
    out = []
    for a, b in runs:
        s, l = a * hop, (b - a) * hop
        if l < pause_min:
            continue
        if s <= 0.02 or s + l >= dur - 0.02:
            continue
        out.append(round(l, 3))
    return out


def level_of(wpg, short_ratio):
    if wpg < 2.0:
        return 1
    if short_ratio >= 0.50 or wpg < 3.0:
        return 2
    if short_ratio >= 0.30:
        return 3
    return 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--wl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="_narr_blocks.json")
    a = ap.parse_args()

    wl = json.load(open(os.path.join(ROOT, a.wl), encoding="utf-8"))
    wl = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in wl.items()}
    b = json.load(open(os.path.join(ROOT, a.ids), encoding="utf-8"))
    ids = [x for blk in b for x in blk["ids"]]

    rows = []
    for sid in ids:
        p = os.path.join(ROOT, a.dir, sid + ".wav")
        if not os.path.exists(p) or sid not in wl:
            continue
        try:
            y, sr = sf.read(p, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            g = gaps(y, sr)
        except Exception:  # noqa: BLE001
            continue
        words = len([w for w in (wl[sid].get("words") or [])
                     if any(c.isalpha() for c in w["w"])])
        if not words:
            continue
        nshort = sum(1 for x in g if x < SHORT_MAX)
        nb = sum(1 for x in g if x >= BOUND_MIN)
        groups = nb + 1
        rows.append(dict(id=sid, words=words, ngap=len(g), nshort=nshort,
                         nbound=nb, groups=groups,
                         wpg=round(words / groups, 2),
                         short_ratio=round(nshort / max(1, len(g)), 3),
                         level=level_of(words / groups, nshort / max(1, len(g)))))

    if not rows:
        print("没有可用条目")
        return

    from collections import Counter
    lv = Counter(r["level"] for r in rows)
    wpg = np.array([r["wpg"] for r in rows], float)
    sr_ = np.array([r["short_ratio"] for r in rows], float)
    print("== %s  n=%d" % (a.dir, len(rows)))
    print("   每调群词数  p10 %.1f / 中位 %.1f / p90 %.1f" %
          (np.percentile(wpg, 10), np.median(wpg), np.percentile(wpg, 90)))
    print("   碎停顿占比  中位 %.2f / p75 %.2f / p90 %.2f" %
          (np.median(sr_), np.percentile(sr_, 75), np.percentile(sr_, 90)))
    tot = sum(lv.values())
    print("   B 维级别分布: " + "  ".join("L%d %d (%.0f%%)" % (k, v, 100.0 * v / tot)
                                          for k, v in sorted(lv.items())))
    p = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    json.dump(dict(dir=a.dir, n=len(rows),
                   level_dist={str(k): v for k, v in lv.items()},
                   rows=rows), open(p, "w", encoding="utf-8"), ensure_ascii=False)
    print("   已写 " + p)


if __name__ == "__main__":
    main()
