# -*- coding: utf-8 -*-
"""_anchor_analyze.py —— 用真人母带建立「强调幅度」的锚点区间。

问题：我们把副词拉长（rate 0.70 ⇒ span ×1.5）或抬高（pitch +9 ⇒ loc +5 半音），
      这个幅度在真人朗读里正常吗？手上没有任何人类参照。

做法：母带 302 条切片（马修朗读，119 wpm）走与 take 完全相同的对齐/测量流程，
      得到「真人每个内容词的句内相对幅度」，再把我们的副词放进去看分位。

★ 为什么主指标是 loc 和 rank，不是 rel（音节时长比）
   rel = 词时长/nsyl ÷ 句内中位。它同时受音素构成影响：
   slowly /sloʊli/ 有两个摩擦/边音，sps 天然偏大；bed /bed/ 的 /b//d/ 是爆破音，
   有声帧极少。真人侧和我们的侧词不同，rel 无法对齐音素偏差。
   - loc（词内 F0 p75 相对本地上下文，半音）与音素无关 ⇒ 主指标
   - rank（词时长在句内的名次）是句内比较，音素偏差被摊到所有词上 ⇒ 辅助
   ★ 句末词有 final lengthening（英语语调固有），必须与句中分开统计。

用法：
    G:/Python310/python.exe _anchor_analyze.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _adv_prom as P   # noqa: E402

ROOT = "G:/_setup"
MIN_WORDS = 4           # 句内内容词少于 4 个，rank 与中位数都不稳（母带切片平均 8.5 词，内容词约 5）
SPS_RATIO_MAX = 3.0     # 单词 sps 超过句中位 3 倍 = 对齐错位（漏词把时长全塞给一个词）


def load_anchor():
    meta = json.load(open(os.path.join(ROOT, "_anchor_meta.json"), encoding="utf-8"))
    asr = {}
    ap = os.path.join(ROOT, "_anchor_asr.json")
    if os.path.exists(ap):
        asr = {os.path.normpath(k): v for k, v in
               json.load(open(ap, encoding="utf-8")).items()}
    return meta, asr


def words_stat(rows):
    """给一行词加上 rel / rank / 是否句末。返回 (list, 句中位 sps) 或 (None, None)。"""
    sps = [r["sps"] for r in rows if r["sps"] > 0]
    if len(sps) < 3:
        return None, None
    med = float(np.median(sps))
    if med <= 0:
        return None, None
    out = []
    for i, r in enumerate(rows):
        if r["sps"] > SPS_RATIO_MAX * med:      # 对齐错位（被漏词撑大）⇒ 整句弃
            return None, None
        out.append(dict(
            w=r["w"], key=r["key"], nsyl=r["nsyl"], sps=round(r["sps"], 4),
            rel=round(r["sps"] / med, 3),
            loc=round(r["loc"], 2) if r["loc"] is not None else None,
            rank=sum(1 for q in rows if q["sps"] > r["sps"]) + 1,
            n=len(rows),
            last=(i >= len(rows) - 2),          # 最后两个内容词算「句末区」
            pos=i + 1))
    return out, med


def collect_anchor():
    meta, asr = load_anchor()
    recs, dropped = [], []
    for wid in sorted(meta):
        m = meta[wid]
        w = os.path.join(ROOT, "_anchor_stage", "_anchor__%s.wav" % wid)
        pr = os.path.join(ROOT, "_wpt_out", "_anchor__%s.prom" % wid)
        if not (os.path.exists(w) and os.path.exists(pr)):
            dropped.append((wid, "no prom"))
            continue
        try:
            rows = P.measure_one(w, pr, m["text"])
        except Exception as e:
            dropped.append((wid, "measure " + str(e)[:40]))
            continue
        if not rows:
            dropped.append((wid, "empty"))
            continue
        # 漏词过滤：ASR 词数 vs 原文字数
        a = asr.get(os.path.normpath(w)) or {}
        n_src = len([x for x in m["text"].replace(",", " ").replace(".", " ").split() if x])
        n_asr = len([x for x in (a.get("words") or []) if str(x.get("w", "")).isalpha()])
        if n_asr and abs(n_src - n_asr) > 1:
            dropped.append((wid, "漏词 原文%d/ASR%d" % (n_src, n_asr)))
            continue
        if len(rows) < MIN_WORDS:
            dropped.append((wid, "内容词仅 %d" % len(rows)))
            continue
        ws, med = words_stat(rows)
        if ws is None:
            dropped.append((wid, "sps 异常"))
            continue
        recs.append(dict(wid=wid, text=m["text"], words=ws, med_sps=med))
    return recs, dropped


def quant(v, name, fmt="%.2f"):
    v = sorted(x for x in v if x is not None)
    if not v:
        print("  %-22s 无数据" % name)
        return
    n = len(v)
    q = lambda p: np.percentile(v, p)
    print(("  %-22s n=%4d  min " + fmt + "  p5 " + fmt + "  p25 " + fmt +
           "  p50 " + fmt + "  p75 " + fmt + "  p90 " + fmt +
           "  p95 " + fmt + "  max " + fmt)
          % (name, n, v[0], q(5), q(25), q(50), q(75), q(90), q(95), v[-1]
             if False else v[-1]))


def main():
    recs, dropped = collect_anchor()
    print("母带可用 %d 句（丢弃 %d）" % (len(recs), len(dropped)))
    from collections import Counter
    print("丢弃原因：", Counter(d[1].split()[0] for d in dropped).most_common())

    allw = [w for r in recs for w in r["words"]]
    mid = [w for w in allw if not w["last"]]
    end = [w for w in allw if w["last"]]
    print("\n内容词 %d 个（句中 %d / 句末 %d）" % (len(allw), len(mid), len(end)))

    print("\n=== 真人词级分布 ===")
    quant([w["rel"] for w in allw], "rel 全句")
    quant([w["rel"] for w in mid], "rel 句中")
    quant([w["rel"] for w in end], "rel 句末")
    quant([w["loc"] for w in allw], "loc 半音 全句")
    quant([w["loc"] for w in mid], "loc 半音 句中")

    # 每句最长的那个词
    tops = []
    for r in recs:
        t = min(r["words"], key=lambda w: w["rank"])
        tops.append(t)
    print("\n=== 真人「句内最长词」===")
    quant([t["rel"] for t in tops], "最长词 rel")
    quant([t["loc"] for t in tops], "最长词 loc 半音")
    print("  位置分布：句末 %d / 句中 %d（%.0f%% 是句末词）"
          % (sum(1 for t in tops if t["last"]),
             sum(1 for t in tops if not t["last"]),
             100 * sum(1 for t in tops if t["last"]) / max(len(tops), 1)))

    print("\n=== 真人「句中区最长词」（排除 final lengthening）===")
    mids = []
    for r in recs:
        m = [w for w in r["words"] if not w["last"]]
        if len(m) >= 3:
            mids.append(min(m, key=lambda w: w["rank"]))
    quant([t["rel"] for t in mids], "最长词 rel")
    quant([t["loc"] for t in mids], "最长词 loc 半音")
    quant([t["rank"] for t in mids], "最长词 rank")

    print("\n=== 真人「loc 最高的词」（音高重音）===")
    hi = []
    for r in recs:
        cand = [w for w in r["words"] if w["loc"] is not None]
        if len(cand) < 4:
            continue
        hi.append(max(cand, key=lambda w: w["loc"]))
    quant([t["loc"] for t in hi], "句内最高 loc")
    quant([t["rel"] for t in hi], "句内最高 loc 词的 rel")

    json.dump(dict(recs=recs, dropped=dropped),
              open(os.path.join(ROOT, "_anchor_words.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写 _anchor_words.json")


if __name__ == "__main__":
    main()
