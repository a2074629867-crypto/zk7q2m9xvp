# -*- coding: utf-8 -*-
"""mc_pause_profile.py —— 统计「马修真人全段」的停顿分布，按标点类型分类。

做法：
  1) 对母带（26.92min / 32kHz）做能量 VAD（-35dB rel peak, 10ms 帧）
  2) 用 v6 标签的切片边界（2-name2text.txt 的文件名含采样点起止）把
     「语音段 → 文本子句」对上，从而知道每个间隙前面是什么标点
  3) 输出 逗号 / 句号 / 破折号 / 分号 各自的停顿中位、分位、样本数
  4) 顺带统计「语音段时长」和「wpm」，用于对比我们的生成音频

用法: python mc_pause_profile.py
"""
import re, json, statistics
from pathlib import Path
import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
LAB = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")
OUTJSON = "G:/_setup/mc_pause_profile.json"
SR = 32000
FRAME = 0.010


def energy_vad(path, thr_db=-35.0, fill_hole=8, drop_island=12):
    """返回 speech mask（10ms/帧）。"""
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    x = x.mean(1)
    assert sr == SR, sr
    hop = int(SR * FRAME)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    sp = db > (db.max() + thr_db)
    m = sp.copy()
    i = 0
    while i < len(m):          # 填掉 <80ms 的洞
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < fill_hole:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):          # 去掉 <120ms 的孤岛
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < drop_island:
                m[i:j] = False
            i = j
        else:
            i += 1
    return m, len(x) / SR


def segments(mask):
    segs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            segs.append((i * FRAME, j * FRAME))
            i = j
        else:
            i += 1
    return segs


def main():
    # ---- 切片标签 ----
    rows = []
    for line in LAB.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        m = re.search(r"_(\d+)_(\d+)\.wav$", p[0])
        if not m:
            continue
        rows.append((int(m.group(1)) / SR, int(m.group(2)) / SR, p[3].strip()))
    rows.sort()
    print("切片 %d 条，覆盖 %.2f~%.2fs" % (len(rows), rows[0][0], rows[-1][1]))

    # ---- VAD ----
    print("能量 VAD 计算中（26.92min）...")
    mask, total = energy_vad(MASTER)
    segs = segments(mask)
    print("语音段 %d 个，总长 %.2fs" % (len(segs), sum(b - a for a, b in segs)))

    # ---- 切片间间隙 + 末标点 ----
    punct_gaps = {}
    all_gaps = []
    for k in range(len(rows) - 1):
        e = rows[k][1]
        s = rows[k + 1][0]
        gap = s - e
        if gap <= 0.02:
            continue
        text = rows[k][2].rstrip()
        if not text:
            continue
        last = text[-1]
        key = {",": "comma", ".": "period", "?": "question", "!": "excl",
               ";": "semicolon", ":": "colon", "-": "dash", "…": "ellipsis"}.get(last, "other:" + last)
        punct_gaps.setdefault(key, []).append(round(gap, 3))
        all_gaps.append(round(gap, 3))

    print()
    print("=" * 74)
    print("真人全段停顿（按切片末标点分类）")
    print("=" * 74)
    print("%-12s %5s %7s %7s %7s %7s %7s" % ("标点", "n", "中位", "均值", "p10", "p90", "max"))
    order = ["period", "comma", "question", "excl", "semicolon", "colon", "dash", "ellipsis"]
    keys = [k for k in order if k in punct_gaps] + [k for k in punct_gaps if k not in order]
    for k in keys:
        v = np.array(punct_gaps[k])
        print("%-12s %5d %7.2f %7.2f %7.2f %7.2f %7.2f" % (
            k, len(v), np.median(v), v.mean(),
            np.percentile(v, 10), np.percentile(v, 90), v.max()))

    g = np.array(all_gaps)
    print()
    print("全部间隙 n=%d  中位 %.2fs  均值 %.2fs  p10 %.2fs  p90 %.2fs  max %.2fs" % (
        len(g), np.median(g), g.mean(), np.percentile(g, 10), np.percentile(g, 90), g.max()))
    print("落在 1.0~2.0s 的比例: %.1f%%   落在 0.85~1.70s 的比例: %.1f%%" % (
        ((g >= 1.0) & (g <= 2.0)).mean() * 100, ((g >= 0.85) & (g <= 1.70)).mean() * 100))

    # ---- 语音段时长与 wpm（用切片文本）----
    seg_durs, wpms = [], []
    for (a, b, t) in rows:
        nw = len(t.split())
        if nw < 2:
            continue
        seg_durs.append(b - a)
        wpms.append(nw / (b - a) * 60)
    print()
    print("切片（语音段）时长: 中位 %.2fs  p10 %.2fs  p90 %.2fs  max %.2fs" % (
        np.median(seg_durs), np.percentile(seg_durs, 10), np.percentile(seg_durs, 90), max(seg_durs)))
    print("切片语速 wpm      : 中位 %.0f   均值 %.0f   p10 %.0f   p90 %.0f" % (
        np.median(wpms), np.mean(wpms), np.percentile(wpms, 10), np.percentile(wpms, 90)))

    # ---- 每句（按句号切）的语速：把切片合并成句子 ----
    sents, cur, cw = [], [], 0
    for (a, b, t) in rows:
        cur.append((a, b, t))
        cw += len(t.split())
        if t.rstrip().endswith((".", "?", "!")):
            sents.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur), cw))
            cur, cw = [], 0
    if cur:
        sents.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur), cw))
    sw = [s[3] / (s[1] - s[0]) * 60 for s in sents if s[3] >= 3]
    print("整句语速 wpm      : 中位 %.0f   均值 %.0f   p10 %.0f   p90 %.0f  (n=%d)" % (
        np.median(sw), np.mean(sw), np.percentile(sw, 10), np.percentile(sw, 90), len(sw)))

    json.dump(dict(total=total, n_seg=len(segs),
                   gaps_by_punct={k: punct_gaps[k] for k in keys},
                   all_gaps=all_gaps,
                   seg_dur_median=float(np.median(seg_durs)),
                   wpm_median=float(np.median(wpms)),
                   sent_wpm_median=float(np.median(sw))),
              open(OUTJSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print()
    print("已写", OUTJSON)


if __name__ == "__main__":
    main()
