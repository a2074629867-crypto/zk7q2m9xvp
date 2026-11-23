# -*- coding: utf-8 -*-
"""真人语料上的 SER 校准：谁真正分得开情绪，谁只是在猜先验。

指标设计（为什么不用简单 accuracy）：
  Expresso 8 种 style 的样本量均衡，但模型输出 9 类，类别空间不对齐，
  直接 accuracy 会把「输出其他类」全判错。这里用三层：
    1) 目标类别召回：只问「该情绪有没有被认出来」（happy/sad 这类明确的）
    2) pairwise AUC：任意两种情绪两两分得开吗（不依赖阈值和先验）
    3) 效应量 Cohen's d：维度模型上，情绪组间差多少个标准差
"""
import json, os, sys, itertools, collections
import numpy as np
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# e2v 中文标签 → 英文键
E2V_MAP = {
    "开心/happy": "happy", "难过/sad": "sad", "生气/angry": "angry",
    "中立/neutral": "neutral", "吃惊/surprised": "surprised",
    "恐惧/fearful": "afraid", "厌恶/disgusted": "disgusted",
    "其他/other": "other", "<unk>": "unk",
}
# Expresso style → 应该被认成哪一类（None = 无对应，不进召回率统计）
TARGET = {
    "happy": {"happy"}, "laughing": {"happy"}, "sad": {"sad"},
    "default": {"neutral"}, "enunciated": {"neutral"},
    "confused": {"surprised", "afraid", "other", "unk", "neutral"},
    "whisper": {"neutral", "other", "unk", "afraid"},
    "emphasis": {"neutral", "angry"},
}


def load(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def cohen_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 3 or nb < 3:
        return 0.0
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 1e-9 else 0.0


def auc(a, b):
    y = np.r_[np.ones(len(a)), np.zeros(len(b))]
    s = np.r_[a, b]
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else 0.5


def rep_e2v(rows):
    print("\n" + "=" * 78)
    print("emotion2vec+ large（真人 745 条）")
    print("=" * 78)
    labs = ["happy", "sad", "angry", "neutral", "surprised", "afraid", "disgusted", "other", "unk"]
    cm = collections.Counter()
    for r in rows:
        lab = E2V_MAP.get(r["score"]["_top"], "other")
        cm[(r["style"], lab)] += 1
    print("%-11s" % "style" + "".join("%-10s" % l[:9] for l in labs) + "  n   recall")
    rec = {}
    for st in sorted(set(r["style"] for r in rows)):
        c = [cm[(st, l)] for l in labs]
        n = sum(c)
        tgt = TARGET.get(st, set())
        k = sum(cm[(st, t)] for t in tgt)
        rec[st] = k / n if n else 0
        print("%-11s" % st + "".join("%-10d" % v for v in c) + "  %-4d %.0f%%" % (n, 100 * rec[st]))
    print("\n目标类召回（越高越好）：")
    for st in ("happy", "laughing", "sad", "default", "enunciated", "confused", "whisper"):
        if st in rec:
            print("  %-11s %.0f%%" % (st, 100 * rec[st]))
    # 混淆对：default vs happy
    print("\n关键混淆（中性 vs 开心）：")
    d = [E2V_MAP[r["score"]["_top"]] for r in rows if r["style"] == "default"]
    h = [E2V_MAP[r["score"]["_top"]] for r in rows if r["style"] == "happy"]
    print("  default → %s" % dict(collections.Counter(d)))
    print("  happy   → %s" % dict(collections.Counter(h)))


def rep_dim(rows):
    print("\n" + "=" * 78)
    print("Vox-Profile 维度头（MSP-Podcast，A/V/D 0-1，真人 745 条）")
    print("=" * 78)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["style"]].append(r["score"])
    print("%-11s %-5s  %-18s %-18s %-18s" % ("style", "n", "arousal", "valence", "dominance"))
    arr = {}
    for st in sorted(by):
        A = np.array([[s["arousal"], s["valence"], s["dominance"]] for s in by[st]])
        arr[st] = A
        f = lambda x: "%.2f [%.2f,%.2f]" % (np.median(x), np.percentile(x, 25), np.percentile(x, 75))
        print("%-11s %-5d  %-18s %-18s %-18s" % (st, len(A), f(A[:, 0]), f(A[:, 1]), f(A[:, 2])))
    print("\npairwise AUC（A=arousal, V=valence；0.5=瞎猜，1.0=完全分开）")
    pairs = [("happy", "sad"), ("happy", "default"), ("sad", "default"),
             ("laughing", "default"), ("confused", "default"), ("whisper", "default")]
    for a, b in pairs:
        if a not in arr or b not in arr:
            continue
        print("  %-10s vs %-10s  A=%.3f  V=%.3f  D=%.3f   d(A)=%+.2f d(V)=%+.2f"
              % (a, b, auc(arr[a][:, 0], arr[b][:, 0]), auc(arr[a][:, 1], arr[b][:, 1]),
                 auc(arr[a][:, 2], arr[b][:, 2]),
                 cohen_d(arr[a][:, 0], arr[b][:, 0]), cohen_d(arr[a][:, 1], arr[b][:, 1])))
    return arr


def rep_phys(rows):
    print("\n" + "=" * 78)
    print("纯物理量（无模型，域外也成立）")
    print("=" * 78)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["style"]].append(r["score"])
    print("%-11s %-5s %-16s %-14s %-14s %-10s" % ("style", "n", "F0 中位[IQR]", "F0 跨度p90-p10", "语音段dBFS", "HNR"))
    for st in sorted(by):
        s = by[st]
        f0 = np.array([x["f0_med"] for x in s])
        span = np.array([x["f0_p90"] - x["f0_p10"] for x in s])
        db = np.array([x["speech_db"] for x in s])
        hn = np.array([x["hnr"] for x in s])
        print("%-11s %-5d %-16s %-14s %-14s %-10s"
              % (st, len(s),
                 "%.0f [%.0f,%.0f]" % (np.median(f0), np.percentile(f0, 25), np.percentile(f0, 75)),
                 "%.0f" % np.median(span), "%.1f" % np.median(db), "%.1f" % np.median(hn)))


def main():
    e2v = load("real_e2v.jsonl")
    dim = load("real_vox_dim.jsonl")
    phy = load("real_phys.jsonl")
    print("样本：e2v=%d  vox_dim=%d  phys=%d" % (len(e2v), len(dim), len(phy)))
    if e2v:
        rep_e2v(e2v)
    if dim:
        rep_dim(dim)
    if phy:
        rep_phys(phy)


if __name__ == "__main__":
    main()
