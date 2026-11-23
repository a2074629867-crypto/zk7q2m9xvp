"""应用人工判定的角色归属（89 个对白块，按顺序）

块内条目的说话人是逐块读原文判出来的，交替规律 + 上下文命名锚点交叉验证。
角色 key 对应音色库：
    Edmund  → Thomas （法语版把 Edmund 改名叫 Thomas，同一角色的音色）
    Charles → Charles
    Joseph  → Joseph  （Edmund 父亲；祖父也用他，同族成年男声）
    Helena  → Helena
    Other   → Helena  （第三章葬礼上别人家的母亲，同女声）
    narrator→ 叙述
"""
import json
import re
from collections import Counter

SRC = r"G:/_setup/_castle_en_ch123.jsonl"
OUT = r"G:/_setup/_castle_en_ch123_cast.jsonl"

E, C, J, H, O = "Edmund", "Charles", "Joseph", "Helena", "Other"

BLOCKS = [
    [J],                                            # 0  father: I will not live there again
    [J, E],                                         # 1
    [J, E, J],                                      # 2  Mr Hooper: Why? / because you are his only grandson
    [E, J],                                         # 3  Edmund: dead old moths / father: not the way to speak
    [E],                                            # 4  that won't be anything new
    [J],                                            # 5  we shall be looking into things
    [J, E, J],                                      # 6  red room
    [J],                                            # 7
    [E, J, E, E, J, J],                             # 8  can I have the key
    [E, J, E, J],                                   # 9  nobody to play cricket / don't like cricket
    [J],                                            # 10 第一个 Joseph Hooper（祖父）
    [J, J],                                         # 11
    [J, J],                                         # 12
    [J],                                            # 13 祖父: this will all belong to you
    [J, J],                                         # 14 祖父
    [J, J],                                         # 15
    [J, E],                                         # 16 butterflies a craze
    [E, J, E, J, E],                                # 17 why didn't you bring me here
    [E],                                            # 18 Death's Head Hawk Moth
    [J],                                            # 19 some people are coming here today
    [J, H],                                         # 20 写信
    [J, J],                                         # 21
    [E],                                            # 22
    [E],                                            # 23
    [E],                                            # 24 it is my house
    [J],                                            # 25 Edmund!
    [J],                                            # 26
    [H],                                            # 27 come along Charles dear
    [H],                                            # 28
    [C],                                            # 29 it's only a pebble
    [E, J],                                         # 30 纸条 / show you to your rooms
    [E],                                            # 31 why did you have to find somewhere new
    [E, C, E, C],                                   # 32 scaredy / when my father dies
    [C],                                            # 33 what then
    [E],                                            # 34 my grandfather died in this room
    [E, C, E, C, E, C, E, C, E, C, E],              # 35 11 条 审问住处
    [C, E, C, E, C, E, C, E, C],                    # 36 9 条 学费/父亲
    [C, E, C, E, C, E, C, E, C, E],                 # 37 10 条（拆出 when did he die）
    [C, E, C],                                      # 38
    [E, C],                                         # 39 he's old
    [E, C],                                         # 40 where do you go to school
    [C, E],                                         # 41
    [C],                                            # 42 Kingshaw said
    [C, E, C, E],                                   # 43 I'm supposed to
    [E, C, E, C, E, C, E, C],                       # 44 8 条
    [E],                                            # 45 you still needn't think you're wanted
    [C],                                            # 46 it is my window now
    [J],                                            # 47 Edmund, why have you locked yourself in
    [J],                                            # 48
    [J],                                            # 49
    [J],                                            # 50
    [J],                                            # 51 but that is not what any battlefield
    [J, E, J, E, J],                                # 52 where is Charles Kingshaw
    [J],                                            # 53
    [E, J],                                         # 54 they will stay for the summer
    [J, E, J],                                      # 55
    [J, E],                                         # 56
    [E, C, E],                                      # 57 you've got to come with me
    [E, C, E, C, E, C],                             # 58
    [H],                                            # 59 Mrs Helena Kingshaw said
    [E, C, E],                                      # 60
    [E],                                            # 61 this is my father's room
    [E, C, E],                                      # 62 you were told to follow me
    [E],                                            # 63 you're just a fool
    [E, C, E, C, E, C, E, C, E, C, E],              # 64 11 条 乌鸦
    [E],                                            # 65 was it a naughty crow
    [E, C, E],                                      # 66
    [E],                                            # 67
    [E, C],                                         # 68
    [E, C, E, C, E, C, E, C, E],                    # 69 9 条 liar
    [E, C],                                         # 70
    [E],                                            # 71 stare you out
    [C],                                            # 72 it's O.K.
    [J, J],                                         # 73 said Mr Joseph Hooper
    [E],                                            # 74 what are you prying at
    [E, C, E, C, E],                                # 75
    [E],                                            # 76 want me to show you
    [E],                                            # 77
    [E],                                            # 78 I've got the key now
    [E],                                            # 79 go on then
    [C, E, C, E],                                   # 80 moths
    [E, E],                                         # 81 open one of the cases
    [C, E, C, E, C, E],                             # 82
    [E],                                            # 83 pick one up
    [E, C, E, C, E, C, E, C],                       # 84
    [E, C, E, C, E, C],                             # 85
    [C, C],                                         # 86 I'm all right / goodnight
    [O, O],                                         # 87 别人家的母亲
    [H],                                            # 88 he is a brave little boy
]

# 叙述句里嵌对白（"He said, '...'"）—— 引号内容占大头就用说话人音色，逐条判过
MIX_BY_ID = {
    "c1_0027": "Joseph",   # He said, I shall be away in London a good deal
    "c1_0049": "Joseph",   # But then, said, No. No, you had really much better be playing cricket
    "c1_0105": "Joseph",   # His father had said, But look at all the others
    "c1_0167": "Joseph",   # Joseph Hooper sighed. That is not the sort of thing to say
    "c2_0251": "Edmund",   # Hooper said Why have you come here?
    "c2_0267": "Edmund",   # He said quietly, Downstairs is something very valuable
    "c2_0326": "Edmund",   # Hooper raised his eyebrows, a hundred schools in Wales
    "c3_0797": "Edmund",   # Hooper said, you can keep it if you like
    "c3_0953": "Charles",  # He wrote home, I like it here very much
}

# 混合条目（叙述 + 引号对白）里的说话人锚点
MIX_PATTERNS = [
    ("Helena", [r"\bMrs\.? Kingshaw\s+(?:had\s+)?said", r"\bMrs Helena Kingshaw\s+(?:had\s+)?said"]),
    ("Joseph", [r"\bMr\.? Hooper\s+(?:had\s+)?said", r"\bJoseph Hooper\s+(?:had\s+)?said",
                r"\bhis father\s+(?:had\s+)?said"]),
    ("Edmund", [r"\bEdmund Hooper\s+(?:had\s+)?said", r"\bEdmund\s+(?:had\s+)?said"]),
    ("Charles", [r"\bKingshaw\s+(?:had\s+)?said", r"\bCharles\s+(?:had\s+)?said"]),
]

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

assert len(blocks) == len(BLOCKS), "block 数不符：%d vs %d" % (len(blocks), len(BLOCKS))

for bi, blk in enumerate(blocks):
    spec = BLOCKS[bi]
    if len(spec) != len(blk):
        print("!! BLK %d 条数不符: 实际 %d 期望 %d  (%s)" % (bi, len(blk), len(spec), rows[blk[0]]["id"]))
        for k, i in enumerate(blk):
            print("     ", k, rows[i]["text"][:80])
        continue
    for i, who in zip(blk, spec):
        rows[i]["speaker"] = who
        rows[i]["conf"] = "MANUAL"

# 混合条目：含引号对白但以叙述开头
for r in rows:
    if r["speaker"]:
        continue
    if r["id"] in MIX_BY_ID:
        r["speaker"] = MIX_BY_ID[r["id"]]
        r["conf"] = "MIX"
        continue
    t = r["text"]
    q = re.findall(r"‘([^’]{25,})’", t)
    if not q:
        continue
    quoted = sum(len(x) for x in q)
    if quoted / max(1, len(t)) < 0.45:
        continue
    for role, pats in MIX_PATTERNS:
        if any(re.search(p, t) for p in pats):
            r["speaker"] = role
            r["conf"] = "MIX"
            break

for r in rows:
    if not r["speaker"]:
        r["speaker"] = "narrator"
        r["conf"] = r.get("conf") or "NARR"

with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("rows", len(rows))
print("conf:", dict(Counter(r["conf"] for r in rows)))
print("speaker:", dict(Counter(r["speaker"] for r in rows)))
sp = Counter(r["speaker"] for r in rows if r["conf"] in ("MANUAL", "MIX"))
print("对白归属:", dict(sp), " total", sum(sp.values()))
