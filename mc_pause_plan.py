# -*- coding: utf-8 -*-
"""mc_pause_plan.py —— 用马修（McConaughey《Wonder》有声书）的实测停顿规则
给任意文本生成停顿计划。

规则来源：G:/_setup/mc_pause_rules.json（26.63min 母带 / 2587 词 / 641 间隙实测）

用法：
  python mc_pause_plan.py --text-file castle40.txt
  python mc_pause_plan.py --text "Three months ago, his grandmother died."
  python mc_pause_plan.py --text-file x.txt --scale 0.85 --jitter 0.12 --tsv
  python mc_pause_plan.py --text-file x.txt --json out.json

规则（全部为「间隙总时长」，即前一语音结束到下一语音开始的静音长度）：
  逗号        1.17s   (p25 1.00 / p75 1.45)
  句号?!      1.76s   (p25 1.38 / p75 1.98)
  分号/冒号   1.28s   (无样本，按逗号 ×1.09 估)
  破折号      1.17s   (同逗号)
  段落末      2.50s   (>=2.3s 超长停 26 例的中位)
  句中换气    0.20s   仅超长无标点句才插；0.43s 用于 >=30 词的分句

关键实测结论：
  · 连词（and/but/so）前**没有**习惯性长停：and 出现 119 次，其中无标点的
    前停顿只有 15 次，中位 0.15s；1.2s 级的 and 前停顿全部来自原文标点
    （句号 10 次 / 逗号 10 次）。→ 不要按「连词」加长停。
  · 逗号/句号的时长与后接词、前子句长度基本无关（1.09~1.37s / 1.59~1.81s）。
  · 唯一显著的分层是段落边界（>=2.3s）。
"""
import argparse
import hashlib
import json
import re
import sys

RULES_PATH = "G:/_setup/mc_pause_rules.json"

# 标点 → (规则键, 兜底中位)
PUNCT_KEY = {
    ",": ("comma", 1.17),
    ".": ("period", 1.76),
    "?": ("question", 1.76),
    "!": ("exclam", 1.76),
    ";": ("semicolon", 1.28),
    ":": ("colon", 1.28),
    "—": ("dash", 1.17),
}
PARA_GAP = 2.50
BREATH_SHORT = 0.20
BREATH_LONG = 0.43

# 句中断点候选（只用于超长无标点句）
SUBORD = set("""that which who whom whose because when while if though although unless
until since as than where whether after before once whereas""".split())
COORD = set("and but or nor yet so for".split())
PREPS = set("""of in on at to with from by about into over under through between across
around like without within upon toward towards against along behind beyond during
except inside outside past off onto unto per via""".split())


def load_rules(path=RULES_PATH):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    return d


def rule_median(rules, key, fallback):
    """从实测 JSON 里取中位数；取不到用兜底。"""
    p = rules.get("punct", {}).get(key)
    if p and p.get("stats"):
        return float(p["stats"]["median"])
    return fallback


def tokenize(text):
    """切成 (word, punct) —— punct 是紧跟在词后的标点串（可能为空）。"""
    out = []
    for raw in text.split():
        m = re.match(r"^(.*?)([,\.\?;:!\u2014\-]+)$", raw)
        if m and m.group(1):
            out.append((m.group(1), m.group(2)))
        else:
            out.append((raw, ""))
    return out


def det_jitter(seed, lo, hi):
    """确定性抖动：同一文本每次跑结果一致。"""
    if hi <= lo:
        return 0.0
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)
    return lo + (hi - lo) * ((h % 10000) / 10000.0)


def plan(text, rules=None, scale=1.0, jitter=0.0, para_gap=True, breath=True):
    rules = rules or {}
    table = {}
    for k, (key, fb) in PUNCT_KEY.items():
        table[k] = rule_median(rules, key, fb)

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    items = []
    gidx = 0
    for pi, para in enumerate(paras):
        toks = tokenize(para)
        nwords = len(toks)
        since_pause = 0
        last_punct_i = -1
        # 记录本段所有标点位置
        marks = [(i, t[1]) for i, t in enumerate(toks) if t[1]]
        for i, (w, p) in enumerate(toks):
            since_pause += 1
            if not p:
                continue
            kind = p[-1]
            base = table.get(kind, 1.17)
            # 段落最后一个标点 = 段落边界
            is_para_end = para_gap and (i == nwords - 1) and (pi < len(paras) - 1)
            target = PARA_GAP if is_para_end else base
            if jitter:
                target += det_jitter("%d:%d:%s" % (pi, i, w), -jitter, jitter)
            items.append(dict(para=pi, idx=i, after=w + p, punct=p,
                              kind="paragraph" if is_para_end else kind,
                              pause_s=round(max(0.0, target * scale), 3)))
            gidx += 1
            since_pause = 0
            last_punct_i = i

        # 超长无标点句：在语法边界补换气
        if breath:
            run_start = 0
            for i, (w, p) in enumerate(toks):
                if p:
                    run_start = i + 1
                    continue
                run_len = i - run_start + 1
                lw = w.lower().strip("'\"")
                if run_len >= 26 and lw in SUBORD:
                    items.append(dict(para=pi, idx=i - 1, after=toks[i - 1][0],
                                      punct="", kind="breath_sub",
                                      pause_s=round(BREATH_SHORT * scale, 3)))
                    run_start = i
                elif run_len >= 30 and lw in COORD:
                    items.append(dict(para=pi, idx=i - 1, after=toks[i - 1][0],
                                      punct="", kind="breath_coord",
                                      pause_s=round(BREATH_SHORT * scale, 3)))
                    run_start = i
                elif run_len >= 34 and lw in PREPS:
                    items.append(dict(para=pi, idx=i - 1, after=toks[i - 1][0],
                                      punct="", kind="breath_prep",
                                      pause_s=round(BREATH_LONG * scale, 3)))
                    run_start = i

    items.sort(key=lambda x: (x["para"], x["idx"]))
    total = sum(x["pause_s"] for x in items)
    return dict(items=items, total_pause_s=round(total, 3),
                n_items=len(items), scale=scale,
                n_paras=len(paras),
                text_sha1=hashlib.sha1(text.encode("utf-8")).hexdigest()[:12])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--jitter", type=float, default=0.0)
    ap.add_argument("--no-para", action="store_true")
    ap.add_argument("--no-breath", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--tsv", action="store_true")
    args = ap.parse_args()

    if args.text_file:
        text = open(args.text_file, encoding="utf-8").read()
    elif args.text:
        text = args.text
    else:
        ap.error("需要 --text 或 --text-file")

    rules = load_rules()
    r = plan(text, rules, scale=args.scale, jitter=args.jitter,
             para_gap=not args.no_para, breath=not args.no_breath)

    if args.json:
        json.dump(r, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出 %s" % args.json)

    if args.tsv:
        print("段\t序\t前词\t标点\t类型\t停顿s")
        for x in r["items"]:
            print("%d\t%d\t%s\t%s\t%s\t%.2f" % (x["para"], x["idx"], x["after"],
                                                x["punct"] or "-", x["kind"], x["pause_s"]))
    else:
        print("段数 %d | 停顿点 %d | 总停顿 %.2fs" %
              (r["n_paras"], r["n_items"], r["total_pause_s"]))
        from collections import Counter
        c = Counter(x["kind"] for x in r["items"])
        for k, v in c.most_common():
            vals = [x["pause_s"] for x in r["items"] if x["kind"] == k]
            print("  %-12s n=%3d  中位 %.2fs" % (k, v, sorted(vals)[len(vals) // 2]))
        print()
        for x in r["items"][:30]:
            print("  %-28s %-6s %5.2fs" % (x["after"][:28], x["kind"], x["pause_s"]))


if __name__ == "__main__":
    main()
