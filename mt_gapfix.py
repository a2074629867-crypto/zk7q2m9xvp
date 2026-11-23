# -*- coding: utf-8 -*-
"""mt_gapfix.py —— 修正拼接停顿（只改 gap，不动音频、不动 id）。

体检发现的两类节奏缺陷：
1. **归属尾巴前是段落停顿**：ch1 有 45 处"旁白…[1.30s]…his father said,"，
   半句话前停 1.3 秒，听感像突然冒出来。→ 改成 0.30s（对白插入口的气口）
2. **小写续句前停顿过长**：同一个句子被按逗号切开，"…windows," 停 1.3 秒再接
   "the oak panelling…"。→ 改成 0.62s（逗号级）

用法：python mt_gapfix.py --plan mt_plan3.json
"""
import argparse
import json
import re
import shutil

ROOT = "G:/_setup"
ATTR = re.compile(r"\b(said|asked|replied|answered|continued|shouted|whispered|"
                  r"added|muttered|responded|cried|told)\b", re.I)
GAP_TAIL = 0.30
GAP_COMMA = 0.62


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="mt_plan3.json")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    path = a.plan if a.plan.startswith("G:") else ROOT + "/" + a.plan
    plan = json.load(open(path, encoding="utf-8"))

    n_tail = n_cont = 0
    for i in range(len(plan) - 1):
        cur, nxt = plan[i], plan[i + 1]
        nt = nxt["text"].strip()
        words = len(nt.split())
        is_tail = words <= 8 and bool(ATTR.search(nt))
        is_cont = nt[:1].islower()
        if is_tail and cur["gap"] > GAP_TAIL + 0.01:
            cur["gap"] = GAP_TAIL
            n_tail += 1
        elif is_cont and cur["gap"] > GAP_COMMA + 0.01:
            cur["gap"] = GAP_COMMA
            n_cont += 1

    if not a.dry:
        shutil.copy2(path, path + ".bak3")
        json.dump(plan, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    gaps = [p["gap"] for p in plan]
    print("%-20s 尾巴前收紧 %d 处  续句收紧 %d 处  → 停顿合计 %.1f 分钟"
          % (a.plan, n_tail, n_cont, sum(gaps) / 60))
    # 读回校验：修复脚本必须证明自己写进去了
    back = json.load(open(path, encoding="utf-8"))
    assert len(back) == len(plan), "写回条数不一致"
    assert sum(p["gap"] for p in back) == sum(gaps), "写回停顿不一致"
    print("   已读回校验通过（%d 条）" % len(back))


if __name__ == "__main__":
    main()
