"""把对白块连同上下文（前 3 条 + 后 2 条）紧凑打印出来，供人工判角色。"""
import json
import sys

SRC = r"G:/_setup/_castle_en_ch123_cast.jsonl"
rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]

blocks, cur = [], []
for i, r in enumerate(rows):
    if r["dialog"]:
        cur.append(i)
    else:
        if cur:
            blocks.append(cur)
            cur = []
if cur:
    blocks.append(cur)

lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
hi = int(sys.argv[2]) if len(sys.argv) > 2 else len(blocks)

print("blocks total", len(blocks), "showing", lo, "-", hi)
for bi in range(lo, min(hi, len(blocks))):
    blk = blocks[bi]
    a = max(0, blk[0] - 3)
    b = min(len(rows), blk[-1] + 3)
    print("\n===== BLK %d  (%s..%s)  n=%d =====" % (bi, rows[blk[0]]["id"], rows[blk[-1]]["id"], len(blk)))
    for i in range(a, b):
        r = rows[i]
        mark = ">>" if r["dialog"] else "  "
        who = r["speaker"] or "?"
        print("%s %-9s %-8s %s" % (mark, r["id"], who, r["text"][:150]))
