# -*- coding: utf-8 -*-
"""
《我是城堡之王》对白归属 v5
============================
相对 v4 的修正（每条都是实测出来的错，不是猜的）

1. ★ 跨段引号：英国小说惯例，同一人连续说话跨段时，中间段不加开引号。
   实测 90 个奇数引号段 = 45 对跨段对白，v4 全部当 mix 丢弃（用户说的「没有引号的」）。
2. ★ 撇号误判：`spiders' webs` / `Kingshaw's` 的撇号被当成引号，导致引号错配。
   规则：`\w'(?=\w)` 词内撇号；`s'(?=\s+[a-z])` 复数所有格；其余才算引号。
3. ★ 段内多句：一段可能含两句分属两人的对白（实测 [2487]），v4 整段只判一条。
   改为按 quote 片段切单元。
4. ★ 心理独白：`he thought, '...'` 带引号但是内心活动（实测 [113]），不算对白。
5. ★ 交替步数：v4 用「段落索引差」算奇偶，中间夹 mix 段就错位。
   改为按「对白单元序列」算，且要求两单元之间没有叙述片段。
6. ★ 呼语漏判：`, Hooper. O.K., I promise.` 不是句尾，v4 漏了（实测 [2056] 判反）。
"""
import json
import re
import sys
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT_JSON = "G:/_setup/castle_dialog_v5.json"
APO = "\x01"

CAST = [
    ("Edmund", ["Edmund", "Hooper", "Master Hooper"]),
    ("Charles", ["Charles", "Kingshaw"]),
    ("Joseph", ["Joseph Hooper", "Mr Hooper", "Joseph"]),
    ("Helena", ["Mrs Kingshaw", "Helena", "Mrs Hooper"]),
    ("Fielding", ["Anthony Fielding", "Fielding", "Anthony"]),
    ("Boland", ["Mrs Boland", "Alice Boland", "Alice"]),
]
ALIAS = sorted([(a, c) for c, al in CAST for a in al], key=lambda x: -len(x[0]))
MALE = {"Edmund", "Charles", "Joseph", "Fielding"}
FEMALE = {"Helena", "Boland"}
KIDS = {"Edmund", "Charles"}

SPEECH = (r"said|asked|replied|answered|continued|shouted|yelled|muttered|"
          r"responded|added|went on|whispered|cried|repeated|told|began|"
          r"called|screamed|sighed|snapped|murmured|observed|remarked|"
          r"explained|agreed|admitted|protested|insisted|urged|begged|"
          r"ordered|announced|declared|suggested|answered back|put in")
THOUGHT = (r"thought|wondered|decided|felt|knew|remembered|imagined|"
           r"realised|realized|considered|reflected|supposed|hoped|feared|"
           r"wished|planned|recalled|dreamed|dreamt|longed|hated|loved")

ATTR_RE = re.compile(r"\b(?:%s)\b" % SPEECH, re.I)
THOUGHT_RE = re.compile(r"\b(?:%s)\b" % THOUGHT, re.I)
SCENE_SHIFT = re.compile(
    r"\b(next morning|next day|that night|in the morning|in the afternoon|"
    r"the following|hours later|when he woke|afterwards|later that|"
    r"at breakfast|at lunch|at tea|at supper|during the night|"
    r"for a moment|for some time|then, one day|one afternoon|one evening)\b",
    re.I)
CHAPTER = re.compile(r"^\s*Chapter\s+\d+", re.I)

VOC_IN = re.compile(r"[,!?]\s*(Hooper|Kingshaw|Charles|Edmund)\s*(?:[.!?,]|$)")
ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)
MOTHER = re.compile(r"\b(his|her|the|my)\s+mother\b", re.I)
FATHER = re.compile(r"\b(his|her|the|my)\s+father\b", re.I)


# ---------------------------------------------------------------- 文本预处理
def protect_apos(t):
    """把撇号换成 \x01，避免被当成引号。分两种：词内撇号、复数所有格。"""
    t = re.sub(r"([A-Za-z])'(?=[A-Za-z])", lambda m: m.group(1) + APO, t)
    t = re.sub(r"([A-Za-z]s)'(?=\s+[a-z])", lambda m: m.group(1) + APO, t)
    return t


def unapo(s):
    return s.replace(APO, "'")


def load_paras():
    t = protect_apos(open(SRC, encoding="utf-8").read())
    raw = [p.strip() for p in t.split("\n\n") if p.strip()]
    # 合并跨段引号：奇数引号段与后续段拼起来，直到配平
    merged, i = [], 0
    while i < len(raw):
        p, idx = raw[i], [i]
        guard = 0
        while p.count("'") % 2 == 1 and i + 1 < len(raw) and guard < 4:
            i += 1
            guard += 1
            p = p + " " + raw[i]
            idx.append(i)
        merged.append(dict(idx=idx, text=p))
        i += 1
    return merged


def find_names(txt):
    """返回按出现顺序的角色名（长别名优先，避免 Mrs Kingshaw 被算成 Charles）"""
    found, used = [], [False] * len(txt)
    for a, c in ALIAS:
        for m in re.finditer(r"\b%s\b" % re.escape(a), txt, re.I):
            if any(used[m.start():m.end()]):
                continue
            for k in range(m.start(), m.end()):
                used[k] = True
            found.append((m.start(), c))
    found.sort()
    return [c for _, c in found]


def split_units(p):
    """把一段拆成 [(kind, text)]，kind ∈ quote / narr。"""
    spans, i, n = [], 0, len(p)
    while i < n:
        if p[i] != "'":
            i += 1
            continue
        j = i + 1
        while j < n:
            if p[j] == "'":
                pv = p[j - 1] if j > 0 else ""
                nx = p[j + 1] if j + 1 < n else ""
                if pv.isalpha() and nx.isalpha():
                    j += 1
                    continue
                break
            j += 1
        if j < n:
            spans.append((i, j))
            i = j + 1
        else:
            i += 1
    out, last = [], 0
    for a, b in spans:
        if a > last:
            out.append(("narr", p[last:a]))
        out.append(("quote", p[a + 1:b]))
        last = b + 1
    if last < len(p):
        out.append(("narr", p[last:]))
    return out


# ---------------------------------------------------------------- 归属
def attr_owner(narr):
    """从一段叙述里取说话人：返回 (who|'M'|'F'|None, how, is_thought)"""
    if not narr or not narr.strip():
        return None, None, False
    is_thought = bool(THOUGHT_RE.search(narr)) and not ATTR_RE.search(narr)
    if ATTR_RE.search(narr):
        # 归属动词前最近的成分
        nm = find_names(narr)
        if nm:
            return nm[-1], "name", False
        m = re.search(r"\b(he|she)\b", narr, re.I)
        if m:
            return ("M" if m.group(1).lower() == "he" else "F"), "pron", False
        return None, "attr-noname", False
    if is_thought:
        return None, "thought", True
    nm = find_names(narr)
    if nm:
        return nm[-1], "name-weak", False
    return None, None, False


def vocative_target(q):
    """引号内呼语：说话人 ≠ 被呼叫者。返回被呼叫者。"""
    m = VOC_IN.search(q)
    if m:
        raw = m.group(1)
        return {"Kingshaw": "Charles", "Hooper": "Edmund"}.get(raw, raw)
    if ADULT_ADDR.search(q):
        return "__ADULT__"
    return None


def main():
    paras = load_paras()
    n = len(paras)
    texts = [unapo(p["text"]) for p in paras]

    # ---- 场景切分：章 + 场景切换信号 ----
    scene = [0] * n
    sid = 0
    for i in range(n):
        if CHAPTER.match(paras[i]["text"]) or (i and SCENE_SHIFT.search(paras[i]["text"][:80])):
            sid += 1
        scene[i] = sid

    # 场景内角色（名字出现 + 母亲/父亲指代 + she 代词）
    scene_cast = defaultdict(set)
    for i in range(n):
        s = scene[i]
        for c in find_names(paras[i]["text"]):
            scene_cast[s].add(c)
        if MOTHER.search(paras[i]["text"]):
            scene_cast[s].add("Helena")
        if FATHER.search(paras[i]["text"]):
            scene_cast[s].add("Joseph")

    # ---- 逐段拆单元 ----
    units = []          # 每条对白一个单元
    para_units = defaultdict(list)   # 段索引 -> 单元下标
    for i in range(n):
        parts = split_units(paras[i]["text"])
        for k, (kind, txt) in enumerate(parts):
            if kind != "quote":
                continue
            prev_narr = parts[k - 1][1] if k > 0 and parts[k - 1][0] == "narr" else ""
            next_narr = parts[k + 1][1] if k + 1 < len(parts) and parts[k + 1][0] == "narr" else ""
            q = unapo(txt).strip()
            if not q or len(re.findall(r"[A-Za-z]+", q)) == 0:
                continue
            who, how, _ = attr_owner(prev_narr)
            if not who:
                w2, h2, _ = attr_owner(next_narr)
                if w2:
                    who, how = w2, (h2 or "") + "-after"
            u = dict(i=i, seq=len(units), text=q, who=who, how=how or "",
                     prev_narr=unapo(prev_narr).strip(), next_narr=unapo(next_narr).strip(),
                     scene=scene[i])
            units.append(u)
            para_units[i].append(len(units) - 1)

    # ---- 心理独白：thought 引导 或 前后叙述都是心理动词 ----
    for u in units:
        if u["who"]:
            continue
        pn, nn = u["prev_narr"], u["next_narr"]
        if (pn and THOUGHT_RE.search(pn) and not ATTR_RE.search(pn)) or \
           (nn and THOUGHT_RE.search(nn) and not ATTR_RE.search(nn)):
            u["who"] = "__THOUGHT__"
            u["how"] = "thought"

    # ---- 代词解析：场景内同性唯一 ----
    for u in units:
        if u["who"] in ("M", "F"):
            pool = MALE if u["who"] == "M" else FEMALE
            cands = [c for c in scene_cast[u["scene"]] if c in pool]
            if len(cands) == 1:
                u["who"] = cands[0]
                u["how"] = "pron-uniq"
            else:
                u["who"], u["how"] = None, "pron-ambig"

    # ---- 呼语：引号内叫对方名字 -> 双人场景下是另一人 ----
    for u in units:
        if u["who"]:
            continue
        tgt = vocative_target(u["text"])
        if not tgt:
            continue
        cands = [c for c in scene_cast[u["scene"]] if c in (MALE | FEMALE)]
        if tgt == "__ADULT__":
            adults = [c for c in cands if c in ("Joseph", "Helena")]
            if len(adults) == 1:
                u["who"], u["how"] = adults[0], "adult-addr"
            continue
        others = [c for c in cands if c != tgt]
        if len(others) == 1:
            u["who"], u["how"] = others[0], "vocative"
        elif len(others) == 2 and tgt in KIDS:
            # 两个候选里排除同性（男孩对男孩说话，另一人仍是男孩）
            same = [c for c in others if (c in MALE) == (tgt in MALE)]
            if len(same) == 1:
                u["who"], u["how"] = same[0], "vocative-sex"

    # ---- 交替：只在对白单元连续、中间无叙述时成立 ----
    def adjacent(u1, u2):
        """两单元之间是否没有叙述插入"""
        if u2["seq"] == u1["seq"] + 1:
            # 同一段内的相邻 quote，中间可能有 narr
            if u1["i"] == u2["i"]:
                return not (u1["next_narr"] or u2["prev_narr"])
            # 相邻段
            return (not u1["next_narr"]) and (not u2["prev_narr"]) and (u2["i"] == u1["i"] + 1)
        return False

    changed = True
    rounds = 0
    while changed and rounds < 12:
        changed = False
        rounds += 1
        for k, u in enumerate(units):
            if u["who"]:
                continue
            cands = [c for c in scene_cast[u["scene"]] if c in (MALE | FEMALE)]
            if len(cands) != 2:
                continue
            for d in (-1, 1):
                kk = k + d
                if not (0 <= kk < len(units)):
                    continue
                v = units[kk]
                if not adjacent(u, v):
                    continue
                if v["who"] in cands:
                    other = [c for c in cands if c != v["who"]]
                    u["who"] = other[0]
                    u["how"] = "alt-%s%d" % ("prev" if d < 0 else "next", abs(d))
                    changed = True
                    break

    # ---- 场景唯一角色兜底 ----
    for u in units:
        if u["who"]:
            continue
        cands = [c for c in scene_cast[u["scene"]] if c in (MALE | FEMALE)]
        if len(cands) == 1:
            u["who"], u["how"] = cands[0], "scene-uniq"

    # ---- 输出 ----
    for u in units:
        if not u["who"]:
            u["who"] = None
            u["conf"] = "UNKNOWN"
        elif u["who"] == "__THOUGHT__":
            u["conf"] = "THOUGHT"
        elif u["how"].startswith(("name", "pron-uniq", "vocative", "adult-addr")):
            u["conf"] = "CONFIRMED"
        elif u["how"].startswith("alt"):
            u["conf"] = "ALTERNATE"
        elif u["how"] == "scene-uniq":
            u["conf"] = "SCENE"
        else:
            u["conf"] = "WEAK"

    cc = Counter(u["conf"] for u in units)
    wc = Counter(u["who"] for u in units)
    print("对白单元 %d（v4 是 1168 段落级）" % len(units))
    for k, v in cc.most_common():
        print("  %-12s %4d  %5.1f%%" % (k, v, 100.0 * v / len(units)))
    print()
    print("角色分布：")
    for k, v in wc.most_common():
        print("  %-10s %4d" % (k, v))
    print()
    print("how 分布：", Counter(u["how"] for u in units).most_common(12))

    json.dump(dict(units=units, stats=dict(total=len(units),
                                           conf=dict(cc), who=dict(wc))),
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % OUT_JSON)


if __name__ == "__main__":
    main()
