# -*- coding: utf-8 -*-
"""用 ch1 的 545 个候选，量化"词级重音从文本能不能预测"。

思路：
  真值 = 实测 prominence（F0 + 能量 + 时长 的句内 robust z 合成，已在 _stress_ch1.json）
  预测规则 = 只用文本可得的信息（内容词 / 位置 / 句末），不看任何音频量
  判据 = 逐词二分类的精确率 / 召回 / F1，以及"句内 top1 是否命中"

注意：本脚本只测"静音规则能到多少"，不训练任何模型。
      目的是给"值不值得上 BERT"一个可比的基线。
"""
import json
import os
from collections import defaultdict

SRC = os.environ.get("STRESS_JSON", "G:/_setup/_stress_ch1.json")

# 阈值：句内 prom 的归一化分位。真值 = 该词 prom 超过句内 p75
TOP_Q = float(os.environ.get("TOP_Q", "0.75"))
# prom 相对值：有些词 f0=0（清音/气声），prom 可能被拉低，故先剔除标点
PUNCT = set(".,;:!?-'\"()[]")


def load():
    d = json.load(open(SRC, encoding="utf-8"))
    out = []
    for k, v in d.items():
        ws = [w for w in v.get("words") or []
              if w.get("w") and w["w"] not in PUNCT and len(w["w"]) > 0]
        if len(ws) < 3:
            continue
        out.append((v.get("uid") or k, v.get("seed"), v.get("n_plan") or len(ws), ws))
    return out


def truth_flags(ws, q=TOP_Q):
    """句内 prom 前 (1-q) 的词记为真重音。"""
    vals = sorted(x["prom"] for x in ws)
    if not vals:
        return [False] * len(ws)
    idx = min(len(vals) - 1, int(q * (len(vals) - 1)))
    thr = vals[idx]
    return [x["prom"] >= thr for x in ws]


def score(pred, gold):
    tp = sum(1 for p, g in zip(pred, gold) if p and g)
    fp = sum(1 for p, g in zip(pred, gold) if p and not g)
    fn = sum(1 for p, g in zip(pred, gold) if not p and g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1, tp, fp, fn


# ---------- 规则集合（全部只用文本） ----------
def r_all_content(ws, i, n):
    return ws[i]["content"]


def r_last_content(ws, i, n):
    """句末实词（end-focus），只看最后一个 content 词。"""
    last = max((j for j in range(n) if ws[j]["content"]), default=-1)
    return i == last


def r_content_nonfirst(ws, i, n):
    return ws[i]["content"] and i > 0


def r_content_last_third(ws, i, n):
    return ws[i]["content"] and i >= n * 2 / 3


def r_content_not_last(ws, i, n):
    last = max((j for j in range(n) if ws[j]["content"]), default=-1)
    return ws[i]["content"] and i != last


def r_long_word(ws, i, n):
    """长词（>=6 字符）——英语重音偏好长内容词。"""
    return ws[i]["content"] and len(ws[i]["w"]) >= 6


def r_content_or_long(ws, i, n):
    return ws[i]["content"] or len(ws[i]["w"]) >= 7


RULES = [
    ("所有内容词", r_all_content),
    ("只标句末实词", r_last_content),
    ("内容词且非首词", r_content_nonfirst),
    ("内容词在后1/3", r_content_last_third),
    ("内容词且非句末", r_content_not_last),
    ("长词(>=6字符)", r_long_word),
    ("内容词 或 超长词", r_content_or_long),
]


def main():
    rows = load()
    print("候选 %d 个，总词数 %d，真值阈值 = 句内 prom p%d"
          % (len(rows), sum(len(r[3]) for r in rows), int(TOP_Q * 100)))

    # 内容词 vs 功能词的 prom 分布
    cont, func = [], []
    for _u, _s, _n, ws in rows:
        for w in ws:
            (cont if w["content"] else func).append(w["prom"])
    q = lambda a, f: sorted(a)[min(len(a) - 1, int(f * (len(a) - 1)))]
    print()
    print("prom 分布：内容词 n=%d 中位 %.2f | 功能词 n=%d 中位 %.2f"
          % (len(cont), q(cont, .5), len(func), q(func, .5)))
    print("           内容词 p25/p75 %.2f/%.2f | 功能词 p25/p75 %.2f/%.2f"
          % (q(cont, .25), q(cont, .75), q(func, .25), q(func, .75)))

    # 逐规则评分
    print()
    print("%-20s %6s %6s %6s   %s" % ("规则", "精确", "召回", "F1", "标为重的比例"))
    print("-" * 62)
    results = []
    for name, fn in RULES:
        P = R = F = 0.0
        tp = fp = fn_ = 0
        npos = ntot = 0
        for _u, _s, _n, ws in rows:
            gold = truth_flags(ws)
            pred = [bool(fn(ws, i, len(ws))) for i in range(len(ws))]
            p, r, f1, a, b, c = score(pred, gold)
            tp += a; fp += b; fn_ += c
            npos += sum(pred); ntot += len(pred)
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn_) if tp + fn_ else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        results.append((f1, name, prec, rec, npos / ntot))
        print("%-20s %5.1f%% %5.1f%% %5.1f%%   %4.1f%%"
              % (name, 100 * prec, 100 * rec, 100 * f1, 100 * npos / ntot))

    # top1 命中：句内 prom 最高的词，是否被规则选中
    print()
    print("=== 句内 top1（最重那个词）命中率 ===")
    for name, fn in RULES:
        hit = tot = 0
        for _u, _s, _n, ws in rows:
            best = max(range(len(ws)), key=lambda i: ws[i]["prom"])
            if not any(fn(ws, i, len(ws)) for i in range(len(ws))):
                continue          # 规则一个都没选，算全漏
            tot += 1
            if fn(ws, best, len(ws)):
                hit += 1
        if tot:
            print("  %-20s %d/%d = %.1f%%" % (name, hit, tot, 100 * hit / tot))

    # 上界：如果完美知道该重哪 3 个词
    print()
    print("=== 上界（若预测器能选中真值前 k 名）===")
    for k in (1, 2, 3):
        tp = fp = fn_ = 0
        for _u, _s, _n, ws in rows:
            gold = truth_flags(ws)
            order = sorted(range(len(ws)), key=lambda i: -ws[i]["prom"])[:k]
            pred = [i in order for i in range(len(ws))]
            p, r, f1, a, b, c = score(pred, gold)
            tp += a; fp += b; fn_ += c
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn_) if tp + fn_ else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        print("  top%d: 精确 %.1f%% 召回 %.1f%% F1 %.1f%%" % (k, 100 * prec, 100 * rec, 100 * f1))

    # 跨 seed 稳定性：同一句不同 seed，prom 最高词的词面是否一致
    print()
    print("=== 跨 seed 稳定性（同一句，不同 seed 的 top1 是否同一个词）===")
    by = defaultdict(list)
    for uid, seed, _n, ws in rows:
        by[uid].append((seed, max(range(len(ws)), key=lambda i: ws[i]["prom"]), ws))
    same = tot = 0
    for uid, lst in by.items():
        if len(lst) < 2:
            continue
        words = [ws[i]["w"].lower() for _s, i, ws in lst]
        tot += 1
        if len(set(words)) == 1:
            same += 1
    if tot:
        print("  %d 句可比，top1 词面完全一致 %d 句 = %.1f%%" % (tot, same, 100 * same / tot))

    # 内容词的 top1 占比
    print()
    print("=== 真值 top1 落在什么词上 ===")
    cn = tn = 0
    for _u, _s, _n, ws in rows:
        best = max(range(len(ws)), key=lambda i: ws[i]["prom"])
        tn += 1
        if ws[best]["content"]:
            cn += 1
    print("  落在内容词上 %d/%d = %.1f%%（随机基线 = 内容词占比）" % (cn, tn, 100 * cn / tn))
    cw = sum(1 for _u, _s, _n, ws in rows for w in ws if w["content"])
    tw = sum(len(ws) for _u, _s, _n, ws in rows)
    print("  内容词占比 %.1f%%" % (100 * cw / tw))


if __name__ == "__main__":
    main()
