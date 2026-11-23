# -*- coding: utf-8 -*-
"""mt_scene.py —— 按文本语义给旁白单元加减停顿（场景/事件影响节奏）。

只动停顿，不动音频本身：生成一次，之后可以任意重排节奏。

规则（都可单独关）：
1. 段落末句      → 基础 1.30s，若该段是「重场景」（死亡/恐惧/寒冷）→ ×1.25
2. 连续短句（<8 词）→ 后面 +0.10s，制造顿挫
3. 长段（>60 词）  → 内部句号停顿 ×0.88，避免拖沓
4. 破折号结尾      → +0.25s（话被打断）
5. 归属尾巴（his father said,）→ 固定 0.30s，不受上面影响

用法：python mt_scene.py --out mt_plan3.json
"""
import argparse
import json
import re

HEAVY = re.compile(
    r"\b(dead|death|died|dying|afraid|fear|frightened|hate|hated|cold|dark|"
    r"kill|blood|ill|sick|stroke|coffin|funeral|grave|silence|empty|alone)\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="G:/_setup/mt_plan2.json")
    ap.add_argument("--out", default="G:/_setup/mt_plan3.json")
    a = ap.parse_args()
    plan = json.load(open(a.src, encoding="utf-8"))

    # 按段落分组（gap==1.30 视为段末）
    paras, cur = [], []
    for p in plan:
        cur.append(p)
        if p["gap"] >= 1.29:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)

    n_heavy = 0
    for para in paras:
        words = sum(len(p["text"].split()) for p in para)
        heavy = sum(1 for p in para if HEAVY.search(p["text"]))
        is_heavy = heavy >= 2
        if is_heavy:
            n_heavy += 1
        for i, p in enumerate(para):
            g = p["gap"]
            if g <= 0.31:                     # 归属尾巴，保持
                continue
            if i == len(para) - 1:            # 段末
                g = 1.30 * (1.25 if is_heavy else 1.0)
            else:
                if words > 60:
                    g *= 0.88
                if len(p["text"].split()) < 8:
                    g += 0.10
                if p["text"].rstrip().endswith(("\u2014", "-")):
                    g += 0.25
                if is_heavy:
                    g *= 1.10
            p["gap"] = round(g, 2)

    json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    gaps = sum(p["gap"] for p in plan)
    print("段落 %d（重场景 %d）  单元 %d  停顿合计 %.1f 分钟"
          % (len(paras), n_heavy, len(plan), gaps / 60))
    for p in plan[:6]:
        print("  %s %.2fs | %s" % (p["id"], p["gap"], p["text"][:70]))


if __name__ == "__main__":
    main()
