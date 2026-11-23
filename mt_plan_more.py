# -*- coding: utf-8 -*-
"""mt_plan_more.py —— 在已抽好的前三章后面追加更多章节（ch4/ch5…）。

复用 mt_plan2 的全部抽取规则（硬换行还原、引号歧义、笔误归一、对白剔除），
只是换 BOUNDS 并把 id 续号，避免和已生成的 N0001… 冲突。

用法：python mt_plan_more.py --chs ch4,ch5 --out mt_plan2b.json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mt_plan2 as P

ROOT = "G:/_setup"
# 章节起止（按 book.txt 的字符偏移，实测 Chapter 标题位置）
MORE = {"ch4": (70725, 93961), "ch5": (93961, 117416),
        "ch6": (117416, 138309), "ch7": (138309, 188054)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chs", default="ch4,ch5")
    ap.add_argument("--base", default="mt_plan2.json")
    ap.add_argument("--out", default="mt_plan2b.json")
    a = ap.parse_args()

    base = json.load(open(os.path.join(ROOT, a.base), encoding="utf-8"))
    nxt = max(int(p["id"][1:]) for p in base) + 1
    raw = open(P.SRC, encoding="utf-8", errors="replace").read()
    plan, leak = list(base), []

    for ch in [c.strip() for c in a.chs.split(",") if c.strip()]:
        if ch not in MORE:
            print("!! 未定义边界：%s" % ch)
            continue
        lo, hi = MORE[ch]
        body = re.sub(r"^Chapter \w+\s*", "", raw[lo:hi])
        n0 = len(plan)
        for par in P.paragraphs(body):
            units = P.para_units(par)
            for ui, (text, gq) in enumerate(units):
                if gq is not None:
                    gap = gq
                elif ui == len(units) - 1:
                    gap = P.GAP_PARA
                elif re.search(r"[.!?\u2026]$", text):
                    gap = P.GAP_PERIOD
                else:
                    gap = P.GAP_COMMA
                if P.is_quote_residue(text):
                    leak.append(text)
                plan.append({"id": "N%04d" % nxt, "ch": ch, "text": text, "gap": gap})
                nxt += 1
        print("%s: %d 单元  %d 词" % (ch, len(plan) - n0,
                                      sum(len(plan[i]["text"].split()) for i in range(n0, len(plan)))))

    json.dump(plan, open(os.path.join(ROOT, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("总计 %d 单元  停顿 %.1f 分钟" % (len(plan), sum(p["gap"] for p in plan) / 60))
    print("含引号残留 %d 条" % len(leak))
    for t in leak[:5]:
        print("  !", t[:80])


if __name__ == "__main__":
    main()
