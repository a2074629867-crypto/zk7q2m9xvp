# -*- coding: utf-8 -*-
"""给旁白逐处停顿边界建标注材料。

为什么不能只用标点档位（REQUIREMENTS 19b 已降级为兜底）：
  `pause_tiers.json` 是「按标点类型给常数」，会把 `Yes. No. Well,` 三处抬成同一个值，
  而要求 19-0 写的是「停顿由 LLM 逐处判定，不给统计常数」，依据是语义与语句自然度。

边界编号：`<句id>#<第几个边界>`，从 1 开始。
只保留句内边界（句末 . ? ! 之后没有内容的不算，那是条与条之间，由拼接器处理）。

输出 `_pause_ctx.jsonl`：
  bid / sid / k / punct / left / right / sent / para
"""
import json
import re

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
OUT = "G:/_setup/_pause_ctx.jsonl"
PUNCT = r"[,;:.?!\u2014\u2013]"
WIN = 7   # 左右各取几个词

rows = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]
rows.sort(key=lambda r: r.get("idx", 0))

# 段落 → 整段文本，提供上下文
para_text = {}
for r in rows:
    key = (r.get("chapter"), r.get("para"))
    para_text.setdefault(key, []).append(r.get("text") or "")

out = []
for r in rows:
    if r.get("speaker") != "narrator":
        continue
    t = r.get("text") or ""
    # 找所有标点位置，跳过句末最后一个（条间停顿）
    marks = list(re.finditer(PUNCT, t))
    if not marks:
        continue
    for k, m in enumerate(marks, 1):
        after = t[m.end():].strip()
        if not after:
            continue          # 句末，条间停顿，不在这里判
        left = t[:m.start()]
        right = after
        lw = left.split()[-WIN:]
        rw = right.split()[:WIN]
        key = (r.get("chapter"), r.get("para"))
        out.append({
            "bid": "%s#%d" % (r["id"], k),
            "sid": r["id"],
            "k": k,
            "punct": m.group(),
            "left": " ".join(lw),
            "right": " ".join(rw),
            "sent": t,
            "para": " ".join(x for x in para_text.get(key, []) if x)[:600],
        })

with open(OUT, "w", encoding="utf-8") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")

print("边界 %d 条 -> %s" % (len(out), OUT))
import collections
print("标点:", dict(collections.Counter(o["punct"] for o in out)))
print("样例:")
for o in out[:2]:
    print("  ", o["bid"], "|", o["left"], "‖", o["punct"], "‖", o["right"])
