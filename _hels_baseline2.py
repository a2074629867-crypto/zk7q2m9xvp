# -*- coding: utf-8 -*-
"""在 Helsinki LibriTTS 标注数据上，量"文本规则预测重音"能到多少。

句子边界 = 句末标点（. ? !），逗号不算。
评估时跳过 NA 行（标点本身）。

对照：
  majority-per-word  ── 论文基线 2-way 80.2% / 3-way 62.4%（train_360）
  BERT-base          ── 论文最好 2-way 83.2% / 3-way 68.6%
  本脚本的规则       ── 看朴素规则离 BERT 有多远，值不值得训模型
"""
import os
from collections import Counter, defaultdict

D = "G:/_setup/_hels"
SENT_END = {".", "?", "!"}

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
there here not
s n't 's
""".split())

# 兼类词不按虚词处理
AMBIG = set("one two three four five six seven eight nine ten half both all".split())


def is_func(w):
    lw = w.lower().strip(".,;:!?\"'()")
    if not lw or lw in AMBIG or lw in ("no", "so", "up", "it", "he", "we", "us", "go"):
        return False
    if lw in FUNC:
        return True
    if len(lw) <= 2:
        return True
    return False


def load(path):
    """返回句子列表；每句是 [(word, prom|None, bnd|None)]，标点保留但 label=None。"""
    sents = []
    cur = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5 or parts[0] == "<file>":
                continue
            w = parts[0]
            pv = None if parts[1] == "NA" else int(parts[1])
            bv = None if parts[2] == "NA" else int(parts[2])
            cur.append((w, pv, bv))
            if pv is None and w in SENT_END:
                sents.append(cur)
                cur = []
    if cur:
        sents.append(cur)
    return sents


def ctx(s):
    """预计算每句的：内容词索引、首/末内容词。"""
    idx = [j for j, x in enumerate(s) if x[1] is not None and not is_func(x[0])]
    return idx, (idx[0] if idx else -1), (idx[-1] if idx else -1)


# ---------------- 规则：返回 0/1/2 ----------------
def r_content(s, i, info):
    w, p, _b = s[i]
    if p is None:
        return None
    return 0 if is_func(w) else 1


def r_last(s, i, info):
    w, p, _b = s[i]
    if p is None:
        return None
    if is_func(w):
        return 0
    return 2 if i == info[2] else 1


def r_last_neg(s, i, info):
    w, p, _b = s[i]
    if p is None:
        return None
    if w.lower() in ("not", "n't", "never", "no", "nothing", "none", "nobody"):
        return 2
    return r_last(s, i, info)


def r_last_neg_first(s, i, info):
    w, p, _b = s[i]
    if p is None:
        return None
    if w.lower() in ("not", "n't", "never", "no", "nothing", "none", "nobody"):
        return 2
    if is_func(w):
        return 0
    return 2 if (i == info[2] or i == info[1]) else 1


def r_last_neg_first_long(s, i, info):
    """+ 长词（>=7 字符）提到 2。"""
    w, p, _b = s[i]
    if p is None:
        return None
    lw = w.lower()
    if lw in ("not", "n't", "never", "no", "nothing", "none", "nobody"):
        return 2
    if is_func(w):
        return 0
    if i == info[2] or i == info[1]:
        return 2
    if len(lw) >= 7:
        return 2
    return 1


RULES = [
    ("内容词=1", r_content),
    ("+句末实词=2", r_last),
    ("+否定词=2", r_last_neg),
    ("+句首实词=2", r_last_neg_first),
    ("+长词(>=7)也算2", r_last_neg_first_long),
]


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def main():
    train = load(os.path.join(D, "train_100.txt"))
    test = load(os.path.join(D, "test.txt"))
    trw = sum(1 for s in train for x in s if x[1] is not None)
    tew = sum(1 for s in test for x in s if x[1] is not None)
    print("train %d 句 / %d 词" % (len(train), trw))
    print("test  %d 句 / %d 词（平均 %.1f 词/句）"
          % (len(test), tew, tew / max(1, len(test))))

    c = Counter()
    for s in test:
        for x in s:
            if x[1] is not None:
                c[x[1]] += 1
    tot = sum(c.values())
    print("test 标签分布: " + "  ".join("%d:%.1f%%" % (k, 100 * v / tot) for k, v in sorted(c.items())))

    # majority-per-word
    stat = defaultdict(Counter)
    glob = Counter()
    for s in train:
        for w, p, _b in s:
            if p is None:
                continue
            stat[w.lower()][p] += 1
            glob[p] += 1
    gmaj = glob.most_common(1)[0][0]

    rows = []
    for s in test:
        info = ctx(s)
        for i, (w, p, _b) in enumerate(s):
            if p is None:
                continue
            pred = stat[w.lower()].most_common(1)[0][0] if stat.get(w.lower()) else gmaj
            rows.append((p, pred, s, i, info))

    print()
    print("%-26s %8s %8s" % ("方法", "3-way", "2-way"))
    print("-" * 46)
    m3 = sum(1 for g, pd, *_ in rows if g == pd)
    m2 = sum(1 for g, pd, *_ in rows if (1 if g else 0) == (1 if pd else 0))
    print("%-26s %7.1f%% %7.1f%%" % ("majority-per-word", pct(m3, len(rows)), pct(m2, len(rows))))
    print("%-26s %7.1f%% %7.1f%%" % ("全猜 0", pct(c[0], tot), pct(c[0] + c[1], tot)))

    for name, fn in RULES:
        a3 = a2 = 0
        for g, _pd, s, i, info in rows:
            pr = fn(s, i, info)
            if pr is None:
                continue
            if g == pr:
                a3 += 1
            if (1 if g else 0) == (1 if pr else 0):
                a2 += 1
        print("%-26s %7.1f%% %7.1f%%" % (name, pct(a3, len(rows)), pct(a2, len(rows))))

    # 困难样本：真值非 0
    hard = [(g, pd) for g, pd, *_ in rows if g != 0]
    print()
    print("=== 只在真值非 0 的词上（共 %d 个，占 %.1f%%）===" % (len(hard), pct(len(hard), len(rows))))
    print("  %-24s %7.1f%%" % ("majority-per-word",
                              pct(sum(1 for g, pd in hard if g == pd), len(hard))))
    for name, fn in RULES:
        a = n = 0
        for g, _pd, s, i, info in rows:
            if g == 0:
                continue
            pr = fn(s, i, info)
            if pr is None:
                continue
            n += 1
            if g == pr:
                a += 1
        print("  %-24s %7.1f%%" % (name, pct(a, n)))

    # 二分类
    print()
    print("=== 二分类（重 vs 不重）===")
    print("%-26s %7s %7s %7s" % ("方法", "精确", "召回", "F1"))
    for name, fn in RULES:
        tp = fp = fnn = 0
        for g, _pd, s, i, info in rows:
            pr = fn(s, i, info)
            if pr is None:
                continue
            P, G = pr > 0, g > 0
            if P and G:
                tp += 1
            elif P:
                fp += 1
            elif G:
                fnn += 1
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fnn) if tp + fnn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        print("%-26s %6.1f%% %6.1f%% %6.1f%%" % (name, 100 * prec, 100 * rec, 100 * f1))

    # 句内 top1 命中（真值最重的词，规则是否选中）
    print()
    print("=== 句内 top1（真值最重的词）规则命中率 ===")
    import statistics
    for name, fn in RULES:
        hit = tot2 = 0
        for s in test:
            info = ctx(s)
            cand = [(i, x[1]) for i, x in enumerate(s) if x[1] is not None]
            if not cand:
                continue
            best = max(cand, key=lambda z: z[1])[0]
            pr = fn(s, best, info)
            if pr is None:
                continue
            tot2 += 1
            if pr == 2:
                hit += 1
        if tot2:
            print("  %-24s %d/%d = %.1f%%" % (name, hit, tot2, pct(hit, tot2)))


if __name__ == "__main__":
    main()
