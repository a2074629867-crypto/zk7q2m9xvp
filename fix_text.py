# -*- coding: utf-8 -*-
"""修正 PDF→EPUB 转换遗留的文本错误（前三章，逐条定点替换，不做全局正则）。

2026-11-10 全量扫描结果（13171 词 / 1912 唯一词）：
- 漏字母型错词：只有 1 处 Turing（epub 原文就错，PDF 断词 "Tur-/ning" 合并失败）
- 连字符丢失：buttercoloured / woodpannelled 各 1 处
- 撇号丢失：wont 1 处
- 断词空格："in to" 3 处（应为 into）
- ill(4) / its(8) 经上下文核对全部正确，不动

用法：python fix_text.py   （改 _castle_en_ch123_cast.jsonl，备份 .bak）
"""
import json
import shutil

SRC = r"G:/_setup/_castle_en_ch123_cast.jsonl"

# id -> [(old, new), ...]
FIX = {
    "c3_0876": [("wont you", "won't you")],
    "c2_0386": [("in to words", "into words")],
    "c2_0406": [("Turing back in to the room", "Turning back into the room")],
    "c3_0845": [("come in to his bedroom", "come into his bedroom")],
    "c3_0560": [("buttercoloured", "butter-coloured")],
    "c1_0024": [("woodpannelled", "wood-pannelled")],
}

rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
shutil.copy2(SRC, SRC + ".bak")
n = 0
for r in rows:
    if r["id"] not in FIX:
        continue
    for old, new in FIX[r["id"]]:
        if old not in r["text"]:
            print("MISS", r["id"], repr(old))
            continue
        r["text"] = r["text"].replace(old, new)
        n += 1
        print("FIX  %-9s %s -> %s" % (r["id"], old, new))

with open(SRC, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("applied", n, "of", sum(len(v) for v in FIX.values()))
