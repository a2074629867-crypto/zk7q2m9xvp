# -*- coding: utf-8 -*-
"""mt_fix_plan.py —— 清理 EPUB 抽取残留的「分页标记」，产出干净计划。

源 txt 里混进 12 处：
    === ch002.xhtml === 第 2 节 第 2 节
夹在正文中间，会被 TTS 逐字念出来（"equals equals equals ch zero zero two xhtml..."）。

规则：
1. 删掉 `=== xxx.xhtml ===` 与 `第 N 节`
2. 折叠多余空格、去首尾空白
3. 清完没内容的单元（整条只有标记）→ 把它的停顿并进上一条，然后删除该单元
4. 用"去掉标记后的原文"逐条回查，确认没有趁机丢字

输出：mt_plan2c.json（干净正文）+ mt_plan3c.json（场景停顿）
用法：python mt_fix_plan.py
"""
import json
import os
import re

ROOT = "G:/_setup"
PAT = re.compile(r"\s*===\s*[\w.]+\.xhtml\s*===\s*|\s*第\s*\d+\s*节\s*")


def clean(t):
    t = PAT.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def main():
    plan = json.load(open(os.path.join(ROOT, "mt_plan2b.json"), encoding="utf-8"))
    out, dropped, fixed = [], [], []
    by_id = {p["id"]: p for p in plan}

    for p in plan:
        t = clean(p["text"])
        if not t or not re.search(r"[A-Za-z]", t):
            dropped.append(p["id"])
            if out:                        # 停顿并进上一条，别把段落节奏弄丢
                out[-1]["gap"] = round(max(out[-1]["gap"], p["gap"]), 2)
            continue
        if t != p["text"]:
            fixed.append((p["id"], p["text"], t))
        q = dict(p)
        q["text"] = t
        out.append(q)

    # 回查：用去标记后的原文校对所有条目
    raw = open("G:/_setup/_book/book.txt", encoding="utf-8", errors="replace").read()
    raw = re.sub(r"\s*===\s*[\w.]+\.xhtml\s*===\s*|\s*第\s*\d+\s*节\s*", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    miss = [p["id"] for p in out if p["text"] not in raw]

    json.dump(out, open(os.path.join(ROOT, "mt_plan2c.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("原 %d 条 → 清 %d 条（改文本 %d，删除 %d，原文查不到 %d）"
          % (len(plan), len(out), len(fixed), len(dropped), len(miss)))
    for i, a, b in fixed:
        print("  %s\n    旧: %s\n    新: %s" % (i, a[:100], b[:100]))
    if dropped:
        print("  删除：", dropped)
    if miss:
        print("  !! 查不到：", miss[:10])


if __name__ == "__main__":
    main()
