"""把城堡之王前三章的旁白按 chunk 切块，供 LLM 判定 rate + 停顿意图。

为什么按 chunk 不按句：
  chapter_run.py 的既有链路是 chunk_sents(target=120, hard_max=165)。
  逐句生成时模型每次独立起句，句间韵律没有连贯性；块内才能形成完整的
  叙述弧线，也才能在块内移植麦康纳的停顿序列。
"""
import json

TARGET = 120
HARD_MAX = 165

rows = [json.loads(l) for l in open("G:/_setup/_castle_en_ch123_plan.jsonl", encoding="utf-8")]
narr = [r for r in rows if r["speaker"] == "narrator"]

# 按章 + 段落顺序切块：只在段落边界断，不跨段
blocks, cur, curw = [], [], 0
for r in narr:
    w = len(r["text"].split())
    # 超硬上限就先把当前块收掉
    if cur and curw + w > HARD_MAX:
        blocks.append(cur)
        cur, curw = [], 0
    cur.append(r)
    curw += w
    # 达到目标词数且正好在段落末尾才收
    if curw >= TARGET:
        blocks.append(cur)
        cur, curw = [], 0
if cur:
    blocks.append(cur)

out = []
for i, b in enumerate(blocks):
    out.append({
        "bid": "B%03d" % i,
        "chapter": b[0]["chapter"],
        "n": len(b),
        "words": sum(len(r["text"].split()) for r in b),
        "ids": [r["id"] for r in b],
        "text": " ".join(r["text"] for r in b),
    })

with open("G:/_setup/_narr_blocks.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

import collections
print("块数 %d，总词 %d" % (len(out), sum(o["words"] for o in out)))
print("每块词数: min %d / 中位 %d / max %d" % (
    min(o["words"] for o in out),
    sorted(o["words"] for o in out)[len(out) // 2],
    max(o["words"] for o in out)))
print("章分布:", dict(collections.Counter(o["chapter"] for o in out)))
print()
for o in out[:3]:
    print("=== %s (%d 句 / %d 词) ===" % (o["bid"], o["n"], o["words"]))
    print(o["text"][:300])
    print()
