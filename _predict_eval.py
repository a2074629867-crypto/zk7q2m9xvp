# -*- coding: utf-8 -*-
"""用 Helsinki LibriTTS 测试集评估 _predict.py 的真实准确率。

与 _hels_baseline2.py 的区别：这里直接调用生产用的 predict()，
确保"评测的"和"要用的"是同一份代码。
"""
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import _predict as P

D = "G:/_setup/_hels"
SENT_END = set(".!?")


def load(path):
    sents, cur = [], []
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5 or parts[0] == "<file>":
            continue
        w = parts[0]
        pv = None if parts[1] == "NA" else int(parts[1])
        cur.append((w, pv))
        if pv is None and w in SENT_END:
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return sents


def main():
    test = load(os.path.join(D, "test.txt"))
    print("test %d 句" % len(test))

    for aggr in (False, True):
        P.AGGRESSIVE = aggr
        n = hit3 = hit2 = 0
        tp = fp = fnn = 0
        top1_hit = top1_tot = 0
        for s in test:
            text = " ".join(w for w, _p in s)
            r = P.predict(text)
            pred_words = [x for x in r["words"] if not x["punct"]]
            gold = [(w, p) for w, p in s if p is not None]
            if len(pred_words) != len(gold):
                continue          # 分词不一致，跳过（应极少）
            for pw, (gw, gp) in zip(pred_words, gold):
                n += 1
                if pw["prom"] == gp:
                    hit3 += 1
                if (1 if pw["prom"] else 0) == (1 if gp else 0):
                    hit2 += 1
                P_, G_ = pw["prom"] > 0, gp > 0
                if P_ and G_:
                    tp += 1
                elif P_:
                    fp += 1
                elif G_:
                    fnn += 1
            # top1
            if not gold:
                continue
            best = max(range(len(gold)), key=lambda i: gold[i][1])
            if pred_words[best]["prom"] == 2:
                top1_hit += 1
            top1_tot += 1

        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fnn) if tp + fnn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        print("\n=== %s 模式 ===" % ("aggressive" if aggr else "conservative"))
        print("  对齐词数 %d" % n)
        print("  3-way 准确 %.1f%%   2-way 准确 %.1f%%" % (100 * hit3 / n, 100 * hit2 / n))
        print("  二分类 精确 %.1f%% 召回 %.1f%% F1 %.1f%%" % (100 * prec, 100 * rec, 100 * f1))
        print("  句内 top1（真值最重词）预测为 2 的比例 %.1f%%（%d/%d）"
              % (100 * top1_hit / top1_tot, top1_hit, top1_tot))


if __name__ == "__main__":
    main()
