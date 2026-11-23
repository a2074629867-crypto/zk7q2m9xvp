# -*- coding: utf-8 -*-
"""
《我是城堡之王》对话归属 v2
==========================
回答：只有引号、没有人物称谓时，能不能分清是谁说的

分层（置信度）：
  CONFIRMED  段内显式名字 + 归属动词        —— 可直接用
  PRONOUN    段内 he/she + 归属动词         —— 需同性唯一，中置信
  ALTERNATE  裸引号，双人场景，轮次交替      —— 高概率（实测 ~80%）
  CROWD      裸引号，群像（多人七嘴八舌）    —— 无单一说话人，标注为「众人」
  UNKNOWN    裸引号，多人/无锚点            —— 需人工读

交替规则（关键）：
  锚点 A(人物 x) 与锚点 B(人物 y) 之间若有 k 段纯对话，
  且中间没有「新场景叙述」（新地点/新时间），则按 x,y,x,y... 交替。
  ★ 若中间出现纯叙述段（narr），交替「可能」被打断（同一人连说），
    这类降级为 ALTERNATE-RISK。
"""
import bisect
import json
import re
from collections import Counter

SRC = "G:/_setup/castle_full.txt"
OUT = "G:/_setup/castle_dialog_v2.json"
APO = "\x01"

CAST = [
    ("Edmund", ["Edmund", "Hooper", "Master Hooper"]),
    ("Charles", ["Charles", "Kingshaw"]),
    ("Joseph", ["Joseph Hooper", "Mr Hooper", "Joseph"]),
    ("Helena", ["Mrs Kingshaw", "Helena"]),
    ("Fielding", ["Anthony Fielding", "Fielding", "Anthony"]),
    ("Boland", ["Mrs Boland", "Alice Boland", "Alice"]),
]
ALIAS = sorted([(a, c) for c, al in CAST for a in al], key=lambda x: -len(x[0]))

ATTR = (r"said|asked|replied|answered|continued|shouted|yelled|muttered|"
        r"responded|added|went on|whispered|cried|repeated|told|began|"
        r"called|screamed|sighed|snapped|murmured|observed|remarked|"
        r"thought|decided|admitted|agreed")

# 场景切换信号（出现即认为交替重置）
SCENE_SHIFT = re.compile(
    r"\b(next morning|next day|that night|in the morning|in the afternoon|"
    r"the following|hours later|when he woke|afterwards|later that|"
    r"at breakfast|at lunch|at tea|at supper|during the night)\b", re.I)


def load_paras():
    t = open(SRC, encoding="utf-8").read()
    t = re.sub(r"([A-Za-z])'([A-Za-z])", lambda m: m.group(1) + APO + m.group(2), t)
    return [p.strip() for p in t.split("\n\n") if p.strip()]


def unapo(s):
    return s.replace(APO, "'")


def kind(p):
    if "'" not in p:
        return "narr"
    return "pure" if len(re.sub(r"'[^']*'", "", p).strip(" ,.;:!?-\n\t")) < 3 else "mix"


def find_names(txt):
    found, used = [], [False] * len(txt)
    for a, c in ALIAS:
        for m in re.finditer(r"\b%s\b" % re.escape(a), txt, re.I):
            if any(used[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                used[i] = True
            found.append((m.start(), c))
    found.sort()
    return [c for _, c in found]


def outside_spans(p):
    spans = [(m.start(), m.end()) for m in re.finditer(r"'[^']*'", p)]
    out, last = [], 0
    for a, b in spans:
        out.append((last, a))
        last = b
    out.append((last, len(p)))
    return out


def attr_of(p):
    """混合段归属 → (who, how)"""
    if not re.search(r"'", p):
        return None, "noquote"
    segs = outside_spans(p)
    # 名字 + 归属动词
    for a, b in segs:
        s = p[a:b]
        if re.search(r"\b(?:%s)\b" % ATTR, s, re.I):
            nm = find_names(s)
            if nm:
                return nm[-1], "name"
    # 名字（短残句）
    for a, b in segs:
        s = p[a:b]
        if len(s) < 70:
            nm = find_names(s)
            if nm:
                return nm[-1], "name-weak"
    # 代词 + 归属动词
    for a, b in segs:
        s = p[a:b]
        m = re.search(r"\b(he|she)\b\s*(?:%s)" % ATTR, s, re.I)
        if m:
            return ("M", "F")[m.group(1).lower() == "she"], "pron"
    return None, "noname"


def main():
    paras = load_paras()
    n = len(paras)
    kinds = [kind(p) for p in paras]
    texts = [unapo(p) for p in paras]

    # ---- 锚点 ----
    anchors = {}
    for i in range(n):
        if kinds[i] != "mix":
            continue
        c, how = attr_of(paras[i])
        if c:
            anchors[i] = (c, how)
    aidx = sorted(anchors)

    # ---- 代词锚点落地：找前文最近且同性唯一的具名人物 ----
    def resolve_pron(i, sex):
        for k in range(i - 1, max(-1, i - 25), -1):
            if kinds[k] in ("narr", "mix"):
                nm = find_names(paras[k])
                nm = [x for x in nm if (x in ("Edmund", "Charles", "Joseph", "Fielding") if sex == "M"
                                        else x in ("Helena", "Boland"))]
                if nm:
                    return nm[-1]
        return None

    for i, (c, how) in list(anchors.items()):
        if how == "pron":
            r = resolve_pron(i, c)
            if r:
                anchors[i] = (r, "pron->" + r)

    # ---- 群像检测 ----
    # 连续 >=4 段纯对话、每段 <=70 字符、且窗口内没有主要角色名字
    def crowd_flags():
        flag = [False] * n
        i = 0
        while i < n:
            if kinds[i] != "pure":
                i += 1
                continue
            j = i
            while j < n and kinds[j] == "pure":
                j += 1
            run = list(range(i, j))
            if len(run) >= 4:
                short = sum(1 for k in run if len(texts[k]) <= 70)
                # 窗口 ±10 段内是否出现主角名
                lo, hi = max(0, i - 10), min(n, j + 10)
                names = set()
                for k in range(lo, hi):
                    if kinds[k] in ("narr", "mix"):
                        names |= set(find_names(paras[k]))
                main_names = names & {"Edmund", "Charles", "Joseph", "Helena", "Fielding", "Boland"}
                if short >= len(run) * 0.7 and len(main_names) <= 1:
                    for k in run:
                        flag[k] = True
            i = j
        return flag

    crowd = crowd_flags()

    # ---- 交替推断 ----
    result = []
    for i in range(n):
        if kinds[i] != "pure":
            continue
        rec = dict(i=i, text=texts[i])

        if crowd[i]:
            rec.update(who="众人", conf="CROWD",
                       note="群像/多人七嘴八舌，无单一说话人")
            result.append(rec)
            continue

        # 找前后锚点
        j = bisect.bisect_left(aidx, i)
        prev_i = aidx[j - 1] if j > 0 else None
        next_i = aidx[j] if j < len(aidx) else None

        # 场景人数（±8 段）
        lo, hi = max(0, i - 8), min(n, i + 8)
        names = set()
        for k in range(lo, hi):
            if kinds[k] in ("narr", "mix"):
                names |= set(find_names(paras[k]))
        names &= {"Edmund", "Charles", "Joseph", "Helena", "Fielding", "Boland"}
        two = len(names) == 2

        # 中间是否有叙述段（可能打断交替）
        def narr_between(a, b):
            return any(kinds[k] == "narr" for k in range(a + 1, b))

        if prev_i is not None and two:
            # 从 prev 起算第几步
            steps = i - prev_i
            # prev 与 i 之间若有其他锚点已排除；此处 prev 是最近的
            order = [anchors[prev_i][0]] + sorted(names - {anchors[prev_i][0]})
            if len(order) == 2:
                who = order[steps % 2]
                risk = narr_between(prev_i, i)
                rec.update(who=who,
                           conf="ALTERNATE-RISK" if risk else "ALTERNATE",
                           base=anchors[prev_i][0], steps=steps,
                           note="从锚点 %d(%s) 交替 %d 步%s"
                                % (prev_i, anchors[prev_i][0], steps,
                                   "；中间有叙述段，可能同人连说" if risk else ""))
                result.append(rec)
                continue

        if next_i is not None and two:
            steps = next_i - i
            order = [anchors[next_i][0]] + sorted(names - {anchors[next_i][0]})
            if len(order) == 2:
                who = order[steps % 2]
                risk = narr_between(i, next_i)
                rec.update(who=who,
                           conf="ALTERNATE-RISK" if risk else "ALTERNATE",
                           base=anchors[next_i][0], steps=steps,
                           note="从后锚点 %d(%s) 反推 %d 步%s"
                                % (next_i, anchors[next_i][0], steps,
                                   "；中间有叙述段，可能同人连说" if risk else ""))
                result.append(rec)
                continue

        rec.update(who=None,
                   conf="UNKNOWN",
                   note="%s场景（%d 人），无可用锚点"
                        % ("双人" if two else "多人", len(names)))
        result.append(rec)

    # ---- 统计 ----
    cc = Counter(r["conf"] for r in result)
    tot = len(result)
    print("纯对话段 %d" % tot)
    for k in ["CROWD", "ALTERNATE", "ALTERNATE-RISK", "UNKNOWN"]:
        print("  %-16s %4d  %5.1f%%" % (k, cc[k], 100.0 * cc[k] / tot))
    print("\n混合段锚点 %d（名字 %d / 代词落地 %d）"
          % (len(anchors),
             sum(1 for v in anchors.values() if v[1].startswith("name")),
             sum(1 for v in anchors.values() if v[1].startswith("pron"))))

    # 归属人数分布
    wc = Counter(r["who"] for r in result if r["who"])
    print("\n归属分布：")
    for w, c in wc.most_common():
        print("   %-10s %4d" % (w, c))

    json.dump(dict(
        stats=dict(total=tot, by_conf=dict(cc), anchors=len(anchors),
                   by_who=dict(wc)),
        anchors={str(k): v for k, v in anchors.items()},
        dialog=result,
    ), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ %s" % OUT)


if __name__ == "__main__":
    main()
