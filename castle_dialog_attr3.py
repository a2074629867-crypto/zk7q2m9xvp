# -*- coding: utf-8 -*-
"""
《我是城堡之王》对话归属 v3
==========================
核心改进（针对 v2 的误判）：
  1. 呼语（vocative）—— 最强信号
     'I'm not afraid of you, Hooper.'  → 说话人 ≠ Hooper，必是 Charles
     'Charles, dear, I don't think...' → 说话人 ≠ Charles，且 darling/dear → 成人
  2. 代词指代落地
     窗口内出现 she/her → 场景加入最近具名女性（Helena/Boland）
     否则 v2 会把母子对话误判成两个男孩
  3. 交替方向修正 + 场景人数按「含代词解析后的在场者」算

置信度：
  VOCATIVE    引号内呼语直接定人          —— 最硬
  CONFIRMED   段内名字 + 归属动词
  PRONOUN     段内 he/she + 归属动词
  ALTERNATE   双人在场，轮次交替
  ALTERNATE-RISK  同上但中间有叙述段
  CROWD       群像
  UNKNOWN     无解
"""
import bisect
import json
import re
from collections import Counter

SRC = "G:/_setup/castle_full.txt"
OUT = "G:/_setup/castle_dialog_v3.json"
APO = "\x01"

MALE = ["Edmund", "Charles", "Joseph", "Fielding"]
FEMALE = ["Helena", "Boland"]
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

# 成人称呼（说这话的必然是 Joseph 或 Helena）
ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)


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
    """
    从引号内容里的呼语判断说话人。
    返回 (who, evidence) 或 (None, None)
    规则：
      ', Hooper' / 'Hooper,'  → Charles
      ', Kingshaw' / 'Kingshaw,' → Edmund
      'Charles, dear' / 'Edmund, ...' → 成人（按上下文男女定）
      darling/dear 无名字 → 成人
    """
    q = quote_text(p)
    if not q:
        return None, None

    # 句首呼语：'Charles, dear, ...' / 'Edmund, you will not...'
    m = re.match(r"^\s*(Charles|Edmund|Kingshaw|Hooper)\s*[,!?]", q)
    if m:
        nm = {"Kingshaw": "Charles", "Hooper": "Edmund"}.get(m.group(1), m.group(1))
        # 说话人 = 另一个
        if ADULT_ADDR.search(q[:40]):
            return ("Helena", "呼语 %s + darling/dear" % m.group(1))
        # 谁称呼 Charles？Edmund 或成人
        if nm == "Charles":
            return ("__ADULT__", "呼语 Charles")
        if nm == "Edmund":
            return ("__ADULT_OR_CHARLES__", "呼语 Edmund")

    # 句尾/句中呼语：'..., Hooper.'
    m = re.search(r"[,!?]\s*(Hooper|Kingshaw)\s*[.!?'\"]?\s*$", q)
    if m:
        if m.group(1) == "Hooper":
            return ("Charles", "呼语 Hooper（句尾）")
        return ("Edmund", "呼语 Kingshaw（句尾）")

    # 句中呼语：'Come on, Kingshaw, it's O.K.'
    m = re.search(r"[,!?]\s*(Hooper|Kingshaw)\s*[,!?]", q)
    if m:
        if m.group(1) == "Hooper":
            return ("Charles", "呼语 Hooper（句中）")
        return ("Edmund", "呼语 Kingshaw（句中）")

    if ADULT_ADDR.search(q):
        return ("__ADULT__", "darling/dear")
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

    # ---------- 场景在场者（含代词解析） ----------
    def scene_cast(i, w=10):
        names = set()
        has_she = False
        for k in range(max(0, i - w), min(n, i + w)):
            names |= set(find_names(paras[k]))
            if re.search(r"\b(she|her)\b", paras[k], re.I):
                has_she = True
        names &= set(MALE + FEMALE)
        if has_she:
            fem = names & set(FEMALE)
            if not fem:
                # 代词 she 出现但没具名女性 → 默认 Helena（Warings 唯一在场女性）
                names.add("Helena")
        return names

    # ---------- 锚点 ----------
    anchors = {}

    # A. 混合段：呼语优先，其次名字/代词
    for i in range(n):
        if kinds[i] != "mix":
            continue
        v, ev = vocative(paras[i])
        if v and v in MALE + FEMALE:
            anchors[i] = (v, "vocative:" + ev)
            continue
        if v == "__ADULT__":
            sc = scene_cast(i, 6)
            cand = [x for x in sc if x in ("Joseph", "Helena")]
            if len(cand) == 1:
                anchors[i] = (cand[0], "vocative:成人称呼")
                continue
        c, how = attr_of(paras[i])
        if c:
            anchors[i] = (c, how)

    # B. 代词锚点落地
    def resolve_pron(i, sex):
        for k in range(i - 1, max(-1, i - 30), -1):
            if kinds[k] in ("narr", "mix"):
                nm = find_names(paras[k])
                pool = MALE if sex == "M" else FEMALE
                nm = [x for x in nm if x in pool]
                if nm:
                    return nm[-1]
        return None

    for i, (c, how) in list(anchors.items()):
        if how == "pron":
            r = resolve_pron(i, c)
            if r:
                anchors[i] = (r, "pron->" + r)
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
            main_names = names & set(MALE + FEMALE)
            if short >= len(run) * 0.7 and len(main_names) <= 1:
                for k in run:
                    crowd[k] = True
        i = j

    # ---------- 逐段归属 ----------
    result = []
    for i in range(n):
        if kinds[i] != "pure":
            continue
        rec = dict(i=i, text=texts[i], who=None, conf="UNKNOWN", note="")

        # 1) 呼语（最硬）
        v, ev = vocative(paras[i])
        if v and v in MALE + FEMALE:
            rec.update(who=v, conf="VOCATIVE", note=ev)
            result.append(rec)
            continue
        if v == "__ADULT__":
            sc = scene_cast(i, 6)
            cand = [x for x in sc if x in ("Joseph", "Helena")]
            if len(cand) == 1:
                rec.update(who=cand[0], conf="VOCATIVE", note="成人称呼 → " + cand[0])
                result.append(rec)
                continue

        if crowd[i]:
            rec.update(who="众人", conf="CROWD", note="群像，无单一说话人")
            result.append(rec)
            continue

        sc = scene_cast(i, 8)
        two = len(sc) == 2

        j = bisect.bisect_left(aidx, i)
        prev_i = aidx[j - 1] if j > 0 else None
        next_i = aidx[j] if j < len(aidx) else None

        def narr_between(a, b):
            return any(kinds[k] == "narr" for k in range(a + 1, b))

        done = False
        for base_i, direction in ((prev_i, "prev"), (next_i, "next")):
            if done or base_i is None or not two:
                continue
            base_who = anchors[base_i][0]
            if base_who not in sc:
                continue
            other = [x for x in sc if x != base_who]
            if len(other) != 1:
                continue
            other = other[0]
            steps = abs(i - base_i)
            who = base_who if steps % 2 == 0 else other
            risk = narr_between(min(i, base_i), max(i, base_i))
            rec.update(who=who,
                       conf="ALTERNATE-RISK" if risk else "ALTERNATE",
                       base=base_i, base_who=base_who, steps=steps,
                       note="%s锚[%d]%s 交替 %d 步%s"
                            % ("前" if direction == "prev" else "后",
                               base_i, base_who, steps,
                               "；中间有叙述段" if risk else ""))
            done = True
        if done:
            result.append(rec)
            continue

        rec.update(who=None, conf="UNKNOWN",
                   note="%s场景(%s)，无锚点"
                        % ("双人" if two else "多人", "/".join(sorted(sc)) or "无人名"))
        result.append(rec)

    # ---------- 统计 ----------
    cc = Counter(r["conf"] for r in result)
    tot = len(result)
    print("纯对话段 %d" % tot)
    for k in ["VOCATIVE", "CROWD", "ALTERNATE", "ALTERNATE-RISK", "UNKNOWN"]:
        print("  %-16s %4d  %5.1f%%" % (k, cc[k], 100.0 * cc[k] / tot))

    # 呼语矛盾自检（应为 0）
    bad = 0
    for r in result:
        if not r["who"] or r["who"] == "众人":
            continue
        for other, nm in [("Charles", "Charles"), ("Edmund", "Edmund")]:
            if other == r["who"]:
                continue
            if re.search(r"[,!?]\s*%s\s*[,!?.]" % nm, r["text"]):
                bad += 1
                break
    print("\n呼语矛盾（应≈0）：%d" % bad)

    wc = Counter(r["who"] for r in result if r["who"])
    print("\n归属分布：")
    for w, c in wc.most_common():
        print("   %-10s %4d" % (w, c))

    json.dump(dict(stats=dict(total=tot, by_conf=dict(cc), by_who=dict(wc),
                              vocative_conflict=bad),
                   anchors={str(k): v for k, v in anchors.items()},
                   dialog=result),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ %s" % OUT)


if __name__ == "__main__":
    main()
