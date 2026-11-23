# -*- coding: utf-8 -*-
"""
《我是城堡之王》对话归属解析器
================================
目的：回答「只有引号、没有人名时，能不能分清是谁说的」

分层：
  L1 段内显式名字    X said, '...'  /  '...' said X        —— 确定
  L2 段内代词        he said, '...' / '...' she said        —— 需前文定位同性唯一
  L3 裸引号 + 双人  轮次交替（锚点之间）                     —— 高概率
  L4 裸引号 + 多人  无法机械判定                             —— 必须人工/模型读上下文

输出：castle_dialog.json  +  统计
"""
import json
import re
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT = "G:/_setup/castle_dialog.json"
APO = "\x01"

# 主要角色（含姓氏/名字/称谓），长优先
CAST = [
    ("Edmund", ["Edmund", "Hooper", "Master Hooper"]),
    ("Charles", ["Charles", "Kingshaw"]),
    ("Joseph", ["Joseph Hooper", "Mr Hooper", "Joseph"]),
    ("Helena", ["Mrs Kingshaw", "Helena"]),
    ("Fielding", ["Anthony Fielding", "Fielding", "Anthony"]),
    ("Boland", ["Mrs Boland", "Alice Boland", "Alice"]),
]
# 长名先匹配，避免 Hooper 吃掉 Mr Hooper
ALIAS = []
for canon, al in CAST:
    for a in al:
        ALIAS.append((a, canon))
ALIAS.sort(key=lambda x: -len(x[0]))

ATTR = (r"said|asked|replied|answered|continued|shouted|yelled|muttered|"
        r"responded|added|went on|whispered|cried|repeated|told|began|"
        r"called|screamed|sighed|snapped|murmured|observed|remarked")

NAME_RX = r"(?:%s)" % "|".join(re.escape(a) for a, _ in ALIAS)


def load_paras():
    t = open(SRC, encoding="utf-8").read()
    t = re.sub(r"([A-Za-z])'([A-Za-z])", lambda m: m.group(1) + APO + m.group(2), t)
    return [p.strip() for p in t.split("\n\n") if p.strip()]


def unapo(s):
    return s.replace(APO, "'")


def quotes(p):
    """返回段落里的引号内容列表"""
    return re.findall(r"'([^']*)'", p)


def rest_after_quotes(p):
    """去掉引号内容后的剩余文字"""
    return re.sub(r"'[^']*'", "", p).strip(" ,.;:!?-\n\t")


def kind(p):
    if "'" not in p:
        return "narr"
    return "pure" if len(rest_after_quotes(p)) < 3 else "mix"


def canon_of(name):
    for a, c in ALIAS:
        if a.lower() == name.lower():
            return c
    return None


def find_names(txt):
    """按长优先抽取人名（不重叠）"""
    found = []
    used = [False] * len(txt)
    for a, c in ALIAS:
        for m in re.finditer(r"\b%s\b" % re.escape(a), txt, re.I):
            if any(used[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                used[i] = True
            found.append((m.start(), c))
    found.sort()
    return [c for _, c in found]


def attr_in_mix(p):
    """
    混合段里找归属。返回 (canon, how) 或 (None, reason)
    how: 'name' | 'pron'
    """
    qs = quotes(p)
    if not qs:
        return None, "noquote"
    # 引号外区域
    spans = [(m.start(), m.end()) for m in re.finditer(r"'[^']*'", p)]
    outside = []
    last = 0
    for a, b in spans:
        outside.append((last, a))
        last = b
    outside.append((last, len(p)))

    # 1) 名字 + 归属动词，且不在引号内
    for a, b in outside:
        seg = p[a:b]
        if re.search(r"\b%s\b" % ATTR, seg, re.I):
            nm = find_names(seg)
            if nm:
                return nm[-1], "name"

    # 2) 名字单独出现（'...' 后跟 "Edmund did not answer." 这种也算弱锚）
    #    只在引号紧邻处找
    for a, b in outside:
        seg = p[a:b]
        if len(seg) < 60:
            nm = find_names(seg)
            if nm:
                return nm[-1], "name-weak"

    # 3) 代词 + 归属动词
    for a, b in outside:
        seg = p[a:b]
        m = re.search(r"\b(he|she)\b\s*(?:%s)" % ATTR, seg, re.I)
        if m:
            return ("M", "F")[m.group(1).lower() == "she"], "pron"
    return None, "noname"


def main():
    paras = load_paras()
    n = len(paras)
    kinds = [kind(p) for p in paras]

    rows = []
    for i, p in enumerate(paras):
        rows.append(dict(i=i, k=kinds[i], txt=unapo(p)[:400]))

    # 段落级锚点
    anchors = {}
    for i, p in enumerate(paras):
        if kinds[i] != "mix":
            continue
        c, how = attr_in_mix(p)
        if c:
            anchors[i] = (c, how)

    print("段落 %d | narr %d | mix %d | pure %d"
          % (n, kinds.count("narr"), kinds.count("mix"), kinds.count("pure")))
    print("混合段锚点：%d / %d" % (len(anchors), kinds.count("mix")))
    print("  其中 名字 %d / 代词 %d"
          % (sum(1 for v in anchors.values() if v[1].startswith("name")),
             sum(1 for v in anchors.values() if v[1] == "pron")))

    # 给每个 pure 段找最近前后锚点
    aidx = sorted(anchors)
    import bisect
    stat = Counter()
    detail = []
    for i in range(n):
        if kinds[i] != "pure":
            continue
        j = bisect.bisect_left(aidx, i)
        prev = aidx[j - 1] if j > 0 else None
        nxt = aidx[j] if j < len(aidx) else None
        dp = i - prev if prev is not None else 999
        dn = nxt - i if nxt is not None else 999

        # 场景人数：前后 30 段内出现的人名集合
        lo, hi = max(0, i - 30), min(n, i + 30)
        cast_set = set()
        for k in range(lo, hi):
            if kinds[k] in ("narr", "mix"):
                for c in find_names(paras[k]):
                    cast_set.add(c)

        two = len(cast_set) <= 2 and len(cast_set) > 0
        if dp <= 3 and two:
            lvl = "L3-near"
        elif two:
            lvl = "L3-far"
        else:
            lvl = "L4-multi"
        stat[lvl] += 1
        detail.append(dict(i=i, prev=prev, next=nxt, dp=dp, dn=dn,
                           cast=sorted(cast_set), lvl=lvl,
                           txt=unapo(paras[i])[:200]))

    print("\n纯对话段归属难度分层：")
    for k in ["L3-near", "L3-far", "L4-multi"]:
        print("  %-10s %4d  (%.1f%%)" % (k, stat[k], 100.0 * stat[k] / max(1, sum(stat.values()))))

    # 场景人数分布
    cc = Counter(len(d["cast"]) for d in detail)
    print("\n纯对话段「前后30段内出现的人物数」分布：")
    for k in sorted(cc):
        print("   %d 人 : %d" % (k, cc[k]))

    json.dump(dict(
        stats=dict(n=n, narr=kinds.count("narr"), mix=kinds.count("mix"),
                   pure=kinds.count("pure"), anchors=len(anchors),
                   levels=dict(stat), cast_size=dict(cc)),
        anchors={str(k): v for k, v in anchors.items()},
        pure=detail,
        rows=rows,
    ), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ %s" % OUT)


if __name__ == "__main__":
    main()
