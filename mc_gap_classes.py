# -*- coding: utf-8 -*-
"""mc_gap_classes.py —— 把马修真人的停顿分成「标点停顿」和「句中换气」两类统计。

分类依据：时长本身是双峰的（<0.3s 与 >1.0s），中间 0.3~0.6 很少。
再用切片文本的标点密度交叉验证，确认长的一类确实是标点位置。

输出 G:/_setup/mc_gap_classes.json，供 pause_by_punct.py 使用。
"""
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
LAB = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")
SR = 32000
OUT = "G:/_setup/mc_gap_classes.json"


def main():
    x, sr = sf.read(MASTER, dtype="float64", always_2d=True)
    x = x.mean(1)
    assert sr == SR
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < 8:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < 12:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    gs = np.array([segs[k][0] - segs[k - 1][1] for k in range(1, len(segs))])
    gs = gs[gs > 0.02]
    print("母带间隙 %d 个  平均 %.3f  中位 %.2f" % (len(gs), gs.mean(), np.median(gs)))

    # 文本标点密度（用于交叉验证分类阈值）
    words, nper, ncom = 0, 0, 0
    for line in LAB.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        t = p[3].strip()
        words += len(t.split())
        nper += t.count(".") + t.count("?") + t.count("!")
        ncom += t.count(",")
    nmarks = nper + ncom
    print("文本 %d 词，句号 %d + 逗号 %d = %d 个标点" % (words, nper, ncom, nmarks))
    print("→ 每 %.2f 词一个标点；母带每 %.2f 词一个间隙" % (words / nmarks, words / len(gs)))

    # 双峰切分：用 0.6s 作界（分桶显示 0.3-0.6 仅 4%，是谷底）
    THR = 0.60
    short = gs[gs < THR]
    long_ = gs[gs >= THR]
    print()
    print("=== 句中换气类（<%.1fs）===" % THR)
    print("  n=%d (%.0f%%)  中位 %.2f  平均 %.2f  p25 %.2f  p75 %.2f  p90 %.2f  max %.2f" % (
        len(short), len(short) / len(gs) * 100, np.median(short), short.mean(),
        np.percentile(short, 25), np.percentile(short, 75),
        np.percentile(short, 90), short.max()))
    print("=== 标点停顿类（>=%.1fs）===" % THR)
    print("  n=%d (%.0f%%)  中位 %.2f  平均 %.2f  p25 %.2f  p75 %.2f  p90 %.2f  max %.2f" % (
        len(long_), len(long_) / len(gs) * 100, np.median(long_), long_.mean(),
        np.percentile(long_, 25), np.percentile(long_, 75),
        np.percentile(long_, 90), long_.max()))

    # 交叉验证：标点类数量应接近标点数
    print()
    print("校验：标点 %d 个 vs 长停顿 %d 个（比值 %.2f）" % (nmarks, len(long_), len(long_) / nmarks))
    print("      句中换气 %d 个，占文本词数每 %.1f 词一次" % (len(short), words / len(short)))

    def stat(a):
        return dict(n=int(len(a)), median=round(float(np.median(a)), 3),
                    mean=round(float(a.mean()), 3),
                    p10=round(float(np.percentile(a, 10)), 3),
                    p25=round(float(np.percentile(a, 25)), 3),
                    p75=round(float(np.percentile(a, 75)), 3),
                    p90=round(float(np.percentile(a, 90)), 3),
                    p95=round(float(np.percentile(a, 95)), 3),
                    max=round(float(a.max()), 3))

    json.dump(dict(thr=THR, total=len(gs), words=words, n_marks=nmarks,
                   short=stat(short), long=stat(long_)),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写", OUT)


if __name__ == "__main__":
    main()
