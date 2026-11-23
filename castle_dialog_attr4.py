# -*- coding: utf-8 -*-
"""
《我是城堡之王》对话归属 v4（定稿）
====================================
回答：只有引号、没有人物称谓时，能不能分清是谁说的

四条归属路径（按可靠性排序）
  1. VOCATIVE   引号内呼语          '..., Hooper.'      → 说话人 ≠ Hooper
  2. ADULT_ADDR 引号内成人称呼      'All right, darling' → Helena/Joseph
  3. ANCHOR     段内名字/代词+归属动词  'X said, ...' / 'he said, ...'
  4. ALTERNATE  双人在场，轮次交替   （分「无叙述间隔」与「跨叙述」两档）
  5. CROWD      群像               无单一说话人
  6. UNKNOWN    无解

修正（相对 v3）
  - 成人候选按「最近距离」取，不再用集合（v3 因窗口内同时出现 Joseph+Helena 而放弃）
  - 加 mother/father 指代：'his mother' → Helena，'his father' → Joseph
  - 呼语放宽：', Hooper is' 这类口语重复主语也算
  - 输出每句的前后文，便于人工复核
"""
import bisect
import json
import re
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT = "G:/_setup/castle_lines.json"
APO = "\x01"

MALE = ["Edmund", "Charles", "Joseph", "Fielding"]
FEMALE = ["Helena", "Boland"]
ADULTS = ["Joseph", "Helena"]
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
        r"called|screamed|sighed|snapped|murmured|observed|remarked")

ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)
MOTHER = re.compile(r"\b(his|her|the|my)\s+mother\b", re.I)
FATHER = re.compile(r"\b(his|her|the|my)\s+father\b", re.I)


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


def quote_text(p):
    return " ".join(re.findall(r"'([^']*)'", p))


def vocative(p):
    q = quote_text(p)
    if not q:
        return None, None

    # 句首呼语
    m = re.match(r"^\s*(Charles|Edmund|Kingshaw|Hooper)\s*[,!?]", q)
    if m:
        raw = m.group(1)
        nm = {"Kingshaw": "Charles", "Hooper": "Edmund"}.get(raw, raw)
        if ADULT_ADDR.search(q[:50]):
            return "__ADULT__", "呼语 %s + darling/dear" % raw
        if nm == "Charles":
            return "__ADULT_OR_EDMUND__", "呼语 Charles"
        return "__ADULT_OR_CHARLES__", "呼语 Edmund"

    # 句尾呼语
    m = re.search(r"[,!?]\s*(Hooper|Kingshaw)\s*[.!?]?\s*$", q)
    if m:
        return ("Charles", "呼语 Hooper（句尾）") if m.group(1) == "Hooper" \
            else ("Edmund", "呼语 Kingshaw（句尾）")

    # 句中呼语
    m = re.search(r"[,!?]\s*(Hooper|Kingshaw)\s*[,!?]", q)
    if m:
        return ("Charles", "呼语 Hooper（句中）") if m.group(1) == "Hooper" \
            else ("Edmund", "呼语 Kingshaw（句中）")

    # 口语重复主语：'He's just stupid, Hooper is'
    m = re.search(r",\s*(Hooper|Kingshaw)\s+(is|was|does|did|has|had)\b", q)
    if m:
        return ("Charles", "重复主语 Hooper") if m.group(1) == "Hooper" \
            else ("Edmund", "重复主语 Kingshaw")

    if ADULT_ADDR.search(q):
        return "__ADULT__", "darling/dear"
    return None, None


def attr_of(p):
    if "'" not in p:
        return None, "noquote"
    spans = [(m.start(), m.end()) for m in re.finditer(r"'[^']*'", p)]
    segs, last = [], 0
    for a, b in spans:
        segs.append((last, a))
        last = b
    segs.append((last, len(p)))
    for a, b in segs:
        s = p[a:b]
        if re.search(r"\b(?:%s)\b" % ATTR, s, re.I):
            nm = find_names(s)
            if nm:
                return nm[-1], "name"
    for a, b in segs:
        s = p[a:b]
        if len(s) < 70:
            nm = find_names(s)
            if nm:
                return nm[-1], "name-weak"
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

    def scene_cast(i, w=8):
        names, has_she = set(), False
        for k in range(max(0, i - w), min(n, i + w)):
            names |= set(find_names(paras[k]))
            if re.search(r"\b(she|her)\b", paras[k], re.I):
                has_she = True
            if MOTHER.search(paras[k]):
                names.add("Helena")
            if FATHER.search(paras[k]):
                names.add("Joseph")
        names &= set(MALE + FEMALE)
        if has_she and not (names & set(FEMALE)):
            names.add("Helena")
        return names

    def nearest_adult(i, w=8):
        """按距离取最近的成人（Joseph/Helena），不是集合"""
        for d in range(0, w + 1):
            for k in (i - d, i + d):
                if 0 <= k < n and kinds[k] in ("narr", "mix"):
                    if MOTHER.search(paras[k]):
                        return "Helena", k
                    if FATHER.search(paras[k]):
                        return "Joseph", k
                    nm = [x for x in find_names(paras[k]) if x in ADULTS]
                    if nm:
                        return nm[-1], k
        return None, None

    # ---------- 锚点 ----------
    anchors = {}
    for i in range(n):
        if kinds[i] != "mix":
            continue
        v, ev = vocative(paras[i])
        if v in MALE + FEMALE:
            anchors[i] = (v, "vocative")
            continue
        if v == "__ADULT__":
            a, _ = nearest_adult(i, 5)
            if a:
                anchors[i] = (a, "adult-addr")
                continue
        c, how = attr_of(paras[i])
        if c:
            anchors[i] = (c, how)

    def resolve_pron(i, sex):
        for k in range(i - 1, max(-1, i - 30), -1):
            if kinds[k] in ("narr", "mix"):
                pool = MALE if sex == "M" else FEMALE
                nm = [x for x in find_names(paras[k]) if x in pool]
                if nm:
                    return nm[-1]
        return None

    for i, (c, how) in list(anchors.items()):
        if how == "pron":
            r = resolve_pron(i, c)
            if r:
                anchors[i] = (r, "pron")
            else:
                del anchors[i]
    aidx = sorted(anchors)

    # ---------- 群像 ----------
    crowd = [False] * n
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
            names = set()
            for k in range(max(0, i - 10), min(n, j + 10)):
                if kinds[k] in ("narr", "mix"):
                    names |= set(find_names(paras[k]))
            if short >= len(run) * 0.7 and len(names & set(MALE + FEMALE)) <= 1:
                for k in run:
                    crowd[k] = True
        i = j

    # ---------- 逐段 ----------
    dialog = []
    for i in range(n):
        if kinds[i] != "pure":
            continue
        rec = dict(i=i, text=texts[i], who=None, conf="UNKNOWN", note="",
                   before=texts[i - 1][:160] if i > 0 else "",
                   after=texts[i + 1][:160] if i + 1 < n else "")

        v, ev = vocative(paras[i])
        if v in MALE + FEMALE:
            rec.update(who=v, conf="VOCATIVE", note=ev)
            dialog.append(rec)
            continue
        if v in ("__ADULT__", "__ADULT_OR_CHARLES__", "__ADULT_OR_EDMUND__"):
            a, _ = nearest_adult(i, 6)
            if a:
                rec.update(who=a, conf="ADULT-ADDR",
                           note=("成人称呼" if v == "__ADULT__" else ev) + " → " + a)
                dialog.append(rec)
                continue

        if crowd[i]:
            rec.update(who="众人", conf="CROWD", note="群像，无单一说话人")
            dialog.append(rec)
            continue

        sc = scene_cast(i, 8)
        two = len(sc) == 2
        j = bisect.bisect_left(aidx, i)
        prev_i = aidx[j - 1] if j > 0 else None
        next_i = aidx[j] if j < len(aidx) else None

        def narr_between(a, b):
            return any(kinds[k] == "narr" for k in range(a + 1, b))

        done = False
        for base_i, tag in ((prev_i, "前"), (next_i, "后")):
            if done or base_i is None or not two:
                continue
            bw = anchors[base_i][0]
            if bw not in sc:
                continue
            other = [x for x in sc if x != bw]
            if len(other) != 1:
                continue
            steps = abs(i - base_i)
            who = bw if steps % 2 == 0 else other[0]
            risk = narr_between(min(i, base_i), max(i, base_i))
            rec.update(who=who,
                       conf="ALTERNATE-RISK" if risk else "ALTERNATE",
                       base=base_i, base_who=bw, steps=steps,
                       note="%s锚[%d]%s 交替%d步%s"
                            % (tag, base_i, bw, steps, "；跨叙述" if risk else ""))
            done = True
        if done:
            dialog.append(rec)
            continue

        rec.update(who=None, conf="UNKNOWN",
                   note="%s场景(%s)" % ("双人" if two else "多人",
                                        "/".join(sorted(sc)) or "无人名"))
        dialog.append(rec)

    # ---------- 统计 ----------
    cc = Counter(r["conf"] for r in dialog)
    tot = len(dialog)
    print("纯对话段 %d（全书段落 %d，混合段 %d）"
          % (tot, n, kinds.count("mix")))
    for k in ["VOCATIVE", "ADULT-ADDR", "ALTERNATE", "ALTERNATE-RISK", "CROWD", "UNKNOWN"]:
        if cc[k]:
            print("  %-16s %4d  %5.1f%%" % (k, cc[k], 100.0 * cc[k] / tot))

    bad = 0
    for r in dialog:
        if not r["who"] or r["who"] == "众人":
            continue
        for nm in ("Charles", "Edmund"):
            if nm == r["who"]:
                continue
            if re.search(r"[,!?]\s*%s\s*[,!?.]" % nm, r["text"]):
                bad += 1
                break
    print("\n呼语矛盾：%d" % bad)

    wc = Counter(r["who"] for r in dialog if r["who"])
    print("\n归属分布：")
    for w, c in wc.most_common():
        print("   %-10s %4d" % (w, c))

    # 按角色分组
    byc = defaultdict(list)
    for r in dialog:
        if r["who"] and r["who"] != "众人":
            byc[r["who"]].append(dict(i=r["i"], text=r["text"],
                                      conf=r["conf"], note=r["note"]))

    json.dump(dict(
        stats=dict(total=tot, paras=n, mix=kinds.count("mix"),
                   by_conf=dict(cc), by_who=dict(wc), conflict=bad),
        dialog=dialog,
        by_character=dict(byc),
    ), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ %s" % OUT)


if __name__ == "__main__":
    main()
