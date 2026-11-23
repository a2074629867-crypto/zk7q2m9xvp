"""英文原著《I'm the King of the Castle》前三章 —— 对白角色归属

原著人物 → 我们音色库的 key：
    Edmund Hooper   → Thomas    （法语版把 Edmund 改名叫 Thomas，音色是同一个孩子）
    Charles Kingshaw→ Charles
    Joseph Hooper   → Joseph    （Edmund 的父亲，51 岁）
    Helena Kingshaw → Helena    （Charles 的母亲，37 岁）
    Mrs Boland      → Boland    （管家，无参考音）
    叙述            → narrator

归属三级推断：
  1) 同一条内有「名字 + said/asked/...」 → 直接定
  2) 同一对白块内有已定条目 → 按 A/B 交替推
  3) 块前一叙述段有「名字 + said」→ 定首条，再交替
  都推不出 → conf=UNKNOWN，单独列出交给人工/语义裁定
"""
import json
import re
import sys
from collections import Counter

SRC = r"G:/_setup/_castle_en_ch123.jsonl"
OUT = r"G:/_setup/_castle_en_ch123_cast.jsonl"
AMB = r"G:/_setup/_castle_en_ambiguous.txt"

# ---------- 人物识别 ----------
# 注意：Hooper 单用 = Edmund（儿子），Mr Hooper = Joseph（父亲）
#       Kingshaw 单用 = Charles，Mrs Kingshaw / Kingshaw's mother = Helena
NAME_PATS = [
    ("Helena", [r"\bMrs\.? Kingshaw\b", r"\bHelena\b", r"\bKingshaw'?s mother\b"]),
    ("Joseph", [r"\bMr\.? Hooper\b", r"\bJoseph Hooper\b", r"\bJoseph\b"]),
    ("Charles", [r"(?<!Mrs\. )(?<!Mrs )\bKingshaw\b(?!'s mother)", r"\bCharles\b"]),
    ("Edmund", [r"\bEdmund Hooper\b", r"\bEdmund\b", r"(?<!Mr\. )(?<!Mr )(?<!Joseph )\bHooper\b"]),
    ("Boland", [r"\bBoland\b"]),
]
SAY = r"(?:had\s+|was\s+|were\s+)?(?:said|says|asked|replied|whispered|shouted|muttered|added|cried|told|answered|observed|went\s+on|put\s+in)"
SAY_RE = re.compile(r"\b(?:said|says|asked|replied|whispered|shouted|muttered|added|cried|told|answered|observed)\b", re.I)

PRONOUN_SAY = re.compile(r"\b(he|she|his father|his mother|the boy|the man|the woman)\s+" + SAY, re.I)


def names_in(text):
    """返回文本中出现的角色（按优先级去重），不含歧义排除。"""
    found = []
    for role, pats in NAME_PATS:
        for p in pats:
            if re.search(p, text):
                found.append(role)
                break
    return found


def speaker_hint(text):
    """同一条内「名字 + said」→ 角色。返回 role 或 None。"""
    if not SAY_RE.search(text):
        return None
    # 优先找紧挨说话动词前面的名字
    for role, pats in NAME_PATS:
        for p in pats:
            if re.search(p + r"[^.]{0,40}?" + SAY, text) or re.search(p + r"\s*,\s*" + SAY, text):
                return role
    # 退而求其次：条内出现唯一一个人名
    ns = names_in(text)
    if len(ns) == 1:
        return ns[0]
    return None


def pronoun_hint(text):
    m = PRONOUN_SAY.search(text)
    if not m:
        return None
    return {"he": "M", "she": "F", "the man": "M", "the woman": "F",
            "his father": "FATHER", "his mother": "MOTHER", "the boy": "BOY"}[m.group(1).lower()]


def resolve_pronoun(kind, prev_role, ctx_roles):
    if kind == "M":
        return prev_role if prev_role in ("Edmund", "Joseph") else None
    if kind == "F":
        return prev_role if prev_role in ("Helena",) else None
    if kind == "FATHER":
        return "Joseph"
    if kind == "MOTHER":
        return "Helena"
    if kind == "BOY":
        return prev_role if prev_role in ("Edmund", "Charles") else None
    return None


def other_party(role, ctx_roles):
    """给定一方，猜对手：本书前三章只有这几种对子。"""
    TABLE = {
        "Edmund": ["Charles", "Joseph", "Helena"],
        "Charles": ["Edmund", "Helena"],
        "Joseph": ["Edmund", "Helena", "Charles"],
        "Helena": ["Charles", "Joseph", "Edmund"],
    }
    for c in TABLE.get(role, []):
        if c in ctx_roles:
            return c
    return TABLE.get(role, [None])[0]


# ---------- 主流程 ----------
rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]

# 全章出现的人物（用来限制候选）
ctx_roles = set()
for r in rows:
    ctx_roles.update(names_in(r["text"]))

# 切对白块
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

for r in rows:
    r["speaker"] = None
    r["conf"] = None

stats = Counter()

for blk in blocks:
    hints = {}
    for i in blk:
        h = speaker_hint(rows[i]["text"])
        if h:
            hints[i] = h
    # 块前一段的提示
    pre = blk[0] - 1
    pre_hint = None
    if pre >= 0 and not rows[pre]["dialog"]:
        pre_hint = speaker_hint(rows[pre]["text"])
        if pre_hint is None:
            pk = pronoun_hint(rows[pre]["text"])
            if pk:
                pre_hint = resolve_pronoun(pk, None, ctx_roles)

    if not hints and pre_hint:
        hints[blk[0]] = pre_hint
        stats["by_pre"] += 1

    if not hints:
        for i in blk:
            rows[i]["conf"] = "UNKNOWN"
            stats["unknown"] += 1
        continue

    # 找到第一个锚点，向前后交替填充
    anchor = min(hints)
    a_role = hints[anchor]
    b_role = None
    # 第二个说话人：块内其他 hint 优先，其次对手表
    for i, h in hints.items():
        if h != a_role:
            b_role = h
            break
    if b_role is None:
        b_role = other_party(a_role, ctx_roles)

    for i in blk:
        rows[i]["speaker"] = a_role if rows[i].get("_hinted_alt") != 1 else b_role
    # 交替分配
    for k, i in enumerate(blk):
        if i in hints:
            rows[i]["speaker"] = hints[i]
            rows[i]["conf"] = "HINT"
        else:
            rows[i]["conf"] = "ALT"
    # 逐个按最近锚点正负交替修正
    last_i, last_role = None, None
    for i in sorted(blk):
        if rows[i]["conf"] == "HINT":
            last_i, last_role = i, rows[i]["speaker"]
    # 从每个锚点向两侧传播
    order = sorted(blk)
    roles = {i: rows[i]["speaker"] for i in order if rows[i]["conf"] == "HINT"}
    if roles:
        first = min(roles)
        # 向前推
        role = roles[first]
        for i in reversed(order[:order.index(first)]):
            role = b_role if role == a_role else a_role
            roles[i] = role
        # 向后推
        role = roles[first]
        for i in order[order.index(first):]:
            if i in roles and rows[i]["conf"] == "HINT":
                role = roles[i]
                continue
            roles[i] = role
            role = b_role if role == a_role else a_role
        for i in order:
            rows[i]["speaker"] = roles.get(i)
            if rows[i]["conf"] != "HINT":
                rows[i]["conf"] = "ALT"

# 叙述
for r in rows:
    if not r["dialog"]:
        r["speaker"] = "narrator"
        r["conf"] = "NARR"

# ---------- 输出 ----------
with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

amb = [r for r in rows if r["conf"] == "UNKNOWN"]
with open(AMB, "w", encoding="utf-8") as f:
    for r in amb:
        f.write("%s\t%s\n" % (r["id"], r["text"]))

print("rows", len(rows))
print("conf:", dict(Counter(r["conf"] for r in rows)))
print("speaker:", dict(Counter(r["speaker"] for r in rows)))
print("UNKNOWN dialog:", len(amb))
print("\n--- UNKNOWN 前 25 条 ---")
for r in amb[:25]:
    print("  %-9s %s" % (r["id"], r["text"][:100]))
