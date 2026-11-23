# -*- coding: utf-8 -*-
"""在 Helsinki LibriTTS 标注数据上，量"文本规则预测重音"能到多少。

对照：
  majority-per-word  ── 论文基线，2-way 80.2% / 3-way 62.4%
  BERT-base          ── 论文最好，2-way 83.2% / 3-way 68.6%
  本脚本的规则       ── 目标：看朴素规则离 BERT 有多远

规则只用：词形（封闭类虚词表）、句内位置、标点。
"""
import os
import re
import sys
from collections import Counter, defaultdict

D = "G:/_setup/_hels"

# 英语封闭类虚词（这些词几乎从不承载核心重音）
FUNC = set("""
a an the
of in to for with on at by from up about into over after beneath under above
across along among around before behind below beside between beyond down during
except inside near off onto outside past since through throughout till toward
towards upon within without
and but or nor so yet because although though while whereas if unless until
when whenever where wherever whether that than as lest once
i me my mine myself you your yours yourself he him his himself she her hers
herself it its itself we us our ours ourselves they them their theirs themselves
this these those who whom whose which what whatever whoever
am is are was were be been being have has had having do does did done doing
will would shall should can could may might must ought need dare used
some any no every each either neither both all few many much more most several
such another other same
there here not to
s s't n't 's
""".split())

# 句首/句中可作虚词的兼类词（这里保守处理，不当虚词）
AMBIG = set("all both half one two three four five six seven eight nine ten".split())


def load(path):
    """返回 [[(word, prom, bnd), ...], ...]，已剔除 NA（标点）。"""
    sents = []
    cur = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts or len(parts) < 5:
                continue
            if parts[0] == "<file>":
                if cur:
                    sents.append(cur)
                cur = []
                continue
            w = parts[0]
            if parts[1] == "NA" or parts[2] == "NA":
                continue
            cur.append((w, int(parts[1]), int(parts[2])))
    if cur:
        sents.append(cur)
    return sents


def is_func(w):
    lw = w.lower().strip(".,;:!?\"'()")
    if not lw or lw in AMBIG:
        return False
    if lw in FUNC:
        return True
    if len(lw) <= 2 and lw not in ("no", "so", "go", "up", "it", "he", "we", "us"):
        return True
    return False


# ---------------- 规则 ----------------
def rule_content(w, i, n, sent):
    """内容词 → 1，功能词 → 0。"""
    return 0 if is_func(w) else 1


def rule_content_last(w, i, n, sent):
    """内容词 → 1；句末最后一个内容词 → 2。"""
    if is_func(w):
        return 0
    last = max((j for j in range(n) if not is_func(sent[j][0])), default=-1)
    return 2 if i == last else 1


def rule_content_last_neg(w, i, n, sent):
    """上一条 + 否定词 → 2。"""
    lw = w.lower()
    if lw in ("not", "n't", "never", "no", "nothing", "none", "nobody", "nowhere"):
        return 2
    return rule_content_last(w, i, n, sent)


def rule_content_last_neg_first(w, i, n, sent):
    """再 + 句首第一个内容词 → 2。"""
    lw = w.lower()
    if lw in ("not", "n't", "never", "no", "nothing", "none", "nobody", "nowhere"):
        return 2
    if is_func(w):
        return 0
    last = max((j for j in range(n) if not is_func(sent[j][0])), default=-1)
    first = min((j for j in range(n) if not is_func(sent[j][0])), default=-1)
    if i == last or i == first:
        return 2
    return 1


RULES = [
    ("内容词=1", rule_content),
    ("内容词1 + 句末实词2", rule_content_last),
    ("+ 否定词2", rule_content_last_neg),
    ("+ 句首实词2", rule_content_last_neg_first),
]


def acc3(pairs):
    return 100.0 * sum(1 for a, b in pairs if a == b) / len(pairs)


def acc2(pairs):
    """2-way：把 2 折成 1。"""
    return 100.0 * sum(1 for a, b in pairs if (1 if a else 0) == (1 if b else 0)) / len(pairs)


def main():
    train = load(os.path.join(D, "train_100.txt"))
    test = load(os.path.join(D, "test.txt"))
    print("train %d 句 / %d 词" % (len(train), sum(len(s) for s in train)))
    print("test  %d 句 / %d 词" % (len(test), sum(len(s) for s in test)))

    # label 分布
    c = Counter()
    for s in test:
        for _w, p, _b in s:
            c[p] += 1
    tot = sum(c.values())
    print("\ntest 3-way 标签分布: " + "  ".join("%d:%.1f%%" % (k, 100 * v / tot) for k, v in sorted(c.items())))

    # majority-per-word 基线（用 train_100 统计）
    stat = defaultdict(Counter)
    for s in train:
        for w, p, _b in s:
            stat[w.lower()][p] += 1
    glob = Counter()
    for s in train:
        for _w, p, _b in s:
            glob[p] += 1
    gmaj = glob.most_common(1)[0][0]

    maj3, maj2 = [], []
    for s in test:
        for w, p, _b in s:
            pred = stat[w.lower()].most_common(1)[0][0] if stat.get(w.lower()) else gmaj
            maj3.append((p, pred))
            maj2.append((p, pred))
    print("\n%-24s %8s %8s" % ("方法", "3-way", "2-way"))
    print("-" * 44)
    print("%-24s %7.1f%% %7.1f%%" % ("majority-per-word", acc3(maj3), acc2(maj2)))

    print("%-24s %7.1f%% %7.1f%%" % ("全猜 0（不看词）", 100 * c[0] / tot,
                                      100 * (c[0] + c[1]) / tot))

    for name, fn in RULES:
        p3, p2 = [], []
        for s in test:
            n = len(s)
            words = [x[0] for x in s]
            for i, (w, p, _b) in enumerate(s):
                pred = fn(w, i, n, s)
                p3.append((p, pred))
                p2.append((p, pred))
        print("%-24s %7.1f%% %7.1f%%" % (name, acc3(p3), acc2(p2)))

    # 只在"真值 != 多数类"的困难样本上比
    print("\n=== 只在真值非 0 的词上（真正需要判该不该重的部分）===")
    hard = [(p, pred) for p, pred in maj3 if p != 0]
    print("  样本 %d 个（占 %.1f%%）" % (len(hard), 100 * len(hard) / len(maj3)))
    print("  majority-per-word 在这些词上: %.1f%%"
          % (100 * sum(1 for a, b in hard if a == b) / len(hard)))
    for name, fn in RULES:
        p3 = []
        for s in test:
            n = len(s)
            for i, (w, p, _b) in enumerate(s):
                if p == 0:
                    continue
                p3.append((p, fn(w, i, n, s)))
        if p3:
            print("  %-22s %.1f%%" % (name, acc3(p3)))

    # 召回 / 精确（把 1、2 都算"重"）
    print("\n=== 二分类：重 vs 不重 ===")
    print("%-24s %8s %8s %8s" % ("方法", "精确", "召回", "F1"))
    for name, fn in RULES:
        tp = fp = fnn = 0
        for s in test:
            n = len(s)
            for i, (w, p, _b) in enumerate(s):
                pred = fn(w, i, n, s) > 0
                gold = p > 0
                if pred and gold: tp += 1
                elif pred: fp += 1
                elif gold: fnn += 1
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fnn) if tp + fnn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        print("%-24s %7.1f%% %7.1f%% %7.1f%%" % (name, 100 * prec, 100 * rec, 100 * f1))


if __name__ == "__main__":
    main()
