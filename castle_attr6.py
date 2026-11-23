# -*- coding: utf-8 -*-
"""
《我是城堡之王》对白归属 v6
============================
在 v5 基础上修三个实测出来的致命问题（v5 UNKNOWN 74%，比 v4 还差）：

1. **`his father said` 认不出来** —— find_names 只认人名，不认亲属指代。
   → 加 KIN 映射：his/her father→Joseph，mother→Helena，the boy→按上下文。
2. **场景 cast 用整章** —— 一章几百段，cast 里挤进全书角色，「双人场景」永不成立。
   → 改为 **对话块（dialogue block）**：连续段落、含引号比例高、无场景切换，
     块的 cast 就是块内提到的角色。交替只在块内 2 人时成立。
3. **代词 `He said` 无法解析** —— 场景内男性不唯一就放弃。
   → 向前找最近叙述段里作主语的人名（句首/动词前），这才是 he 的真实指向。

v5 保留的正确改进：跨段引号合并、撇号保护、段内多句切分、心理独白排除。
"""
import json
import re
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT_JSON = "G:/_setup/castle_dialog_v6.json"
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
ADULTS = {"Joseph", "Helena", "Fielding", "Boland"}

SPEECH = (r"said|asked|replied|answered|continued|shouted|yelled|muttered|"
          r"responded|added|went on|whispered|cried|repeated|told|began|"
          r"called|screamed|sighed|snapped|murmured|observed|remarked|"
          r"explained|agreed|admitted|protested|insisted|urged|begged|"
          r"ordered|announced|declared|suggested|put in|broke in|went")
THOUGHT = (r"thought|wondered|decided|felt|knew|remembered|imagined|"
           r"realised|realized|considered|reflected|supposed|hoped|feared|"
           r"wished|planned|recalled|dreamed|dreamt|longed|hated|loved")

ATTR_RE = re.compile(r"\b(?:%s)\b" % SPEECH, re.I)
THOUGHT_RE = re.compile(r"\b(?:%s)\b" % THOUGHT, re.I)
SCENE_SHIFT = re.compile(
    r"\b(next morning|next day|that night|in the morning|in the afternoon|"
    r"the following|hours later|when he woke|afterwards|later that|"
    r"at breakfast|at lunch|at tea|at supper|during the night)\b", re.I)
CHAPTER = re.compile(r"^\s*Chapter\s+\d+", re.I)

VOC_IN = re.compile(r"[,!?]\s*(Hooper|Kingshaw|Charles|Edmund)\s*(?:[.!?,]|$)")
ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)
KIN = [
    (re.compile(r"\b(his|her|the|my)\s+father\b", re.I), "Joseph"),
    (re.compile(r"\b(his|her|the|my)\s+mother\b", re.I), "Helena"),
    (re.compile(r"\b(Mrs|Mr)\s+Hooper\b", re.I), None),   # 已由 ALIAS 处理
]


def protect_apos(t):
    t = re.sub(r"([A-Za-z])'(?=[A-Za-z])", lambda m: m.group(1) + APO, t)
    t = re.sub(r"([A-Za-z]s)'(?=\s+[a-z])", lambda m: m.group(1) + APO, t)
    return t


def unapo(s):
    return s.replace(APO, "'")


def load_paras():
    t = protect_apos(open(SRC, encoding="utf-8").read())
    raw = [p.strip() for p in t.split("\n\n") if p.strip()]
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


def find_kin(txt):
    out = []
    for rx, who in KIN:
        if who and rx.search(txt):
            out.append(who)
    return out


def split_units(p):
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


def main():
    paras = load_paras()
    n = len(paras)
    texts = [unapo(p["text"]) for p in paras]
    has_q = [("'" in p["text"]) for p in paras]

    # ---------------- 对话块 ----------------
    # 连续段落，允许夹入短叙述段（<=200 字），遇章节/场景切换/长叙述断开
    block = [0] * n
    bid = 0
    gap = 0
    for i in range(n):
        if CHAPTER.match(paras[i]["text"]) or SCENE_SHIFT.search(paras[i]["text"][:80]):
            bid += 1
            gap = 0
            block[i] = bid
            continue
        if not has_q[i] and len(texts[i]) > 200:
            gap += 1
            if gap >= 2:
                bid += 1
                gap = 0
        elif has_q[i]:
            gap = 0
        block[i] = bid

    bcast = defaultdict(set)
    for i in range(n):
        b = block[i]
        bcast[b] |= set(find_names(paras[i]["text"])) | set(find_kin(paras[i]["text"]))
        if re.search(r"\b(she|her|hers)\b", paras[i]["text"], re.I):
            bcast[b].add("__F__")
        if re.search(r"\b(he|him|his)\b", paras[i]["text"], re.I):
            bcast[b].add("__M__")

    def block_cast(i):
        s = set(bcast[block[i]])
        # __F__ 提示但块内没有女性名 -> 可能是 Helena/Boland，不硬加
        return s & (MALE | FEMALE)

    # ---------------- 拆单元 ----------------
    units = []
    for i in range(n):
        parts = split_units(paras[i]["text"])
        for k, (kind, txt) in enumerate(parts):
            if kind != "quote":
                continue
            pn = parts[k - 1][1] if k > 0 and parts[k - 1][0] == "narr" else ""
            nn = parts[k + 1][1] if k + 1 < len(parts) and parts[k + 1][0] == "narr" else ""
            q = unapo(txt).strip()
            if not re.search(r"[A-Za-z]", q):
                continue
            units.append(dict(i=i, seq=len(units), text=q, who=None, how="",
                              prev_narr=unapo(pn).strip(), next_narr=unapo(nn).strip(),
                              block=block[i]))
    para_first = {}
    para_last = {}
    for u in units:
        para_first.setdefault(u["i"], u["seq"])
        para_last[u["i"]] = u["seq"]

    # ---------------- 归属：同段叙述 ----------------
    def owner_of(narr):
        """返回 (who, how)。who 可能是 M/F 待解析。"""
        if not narr or not narr.strip():
            return None, None
        has_attr = bool(ATTR_RE.search(narr))
        nm = find_names(narr)
        kin = find_kin(narr)
        if has_attr:
            if nm:
                return nm[-1], "name"
            if kin:
                return kin[-1], "kin"
            m = re.search(r"\b(he|she)\b", narr, re.I)
            if m:
                return ("M" if m.group(1).lower() == "he" else "F"), "pron"
            return None, "attr-noname"
        if THOUGHT_RE.search(narr):
            return None, "thought"
        if nm:
            return nm[-1], "name-weak"
        if kin:
            return kin[-1], "kin-weak"
        return None, None

    for u in units:
        w, how = owner_of(u["prev_narr"])
        if not w:
            w2, h2 = owner_of(u["next_narr"])
            if w2:
                w, how = w2, (h2 or "") + "-after"
        if w:
            u["who"], u["how"] = w, how or ""

    # ---------------- 心理独白 ----------------
    for u in units:
        if u["who"]:
            continue
        for s in (u["prev_narr"], u["next_narr"]):
            if s and THOUGHT_RE.search(s) and not ATTR_RE.search(s):
                u["who"], u["how"] = "__THOUGHT__", "thought"
                break

    # ---------------- 跨段归属：紧邻段落的叙述 ----------------
    def para_narr(j, side):
        """取第 j 段的首/尾叙述片段"""
        if not (0 <= j < n):
            return ""
        parts = split_units(paras[j]["text"])
        if side == "tail":
            for kind, t in reversed(parts):
                if kind == "narr":
                    return unapo(t).strip()
            return ""
        for kind, t in parts:
            if kind == "narr":
                return unapo(t).strip()
        return ""

    for u in units:
        if u["who"]:
            continue
        for j, side, tag in ((u["i"] - 1, "tail", "prevpara"),
                             (u["i"] + 1, "head", "nextpara")):
            s = para_narr(j, side)
            if not s or len(s) > 220:
                continue
            w, how = owner_of(s)
            if w and w != "__THOUGHT__":
                u["who"], u["how"] = w, "%s-%s" % (how or "", tag)
                break

    # ---------------- 代词解析 ----------------
    def pron_target(i, sex):
        """向前找最近叙述段里作主语的人名"""
        pool = MALE if sex == "M" else FEMALE
        for k in range(i, max(-1, i - 8), -1):
            s = texts[k]
            if k == i:
                continue
            for m in re.finditer(r"(?:^|[.!?]\s+|,\s+)([A-Z][a-z]+)\b", s):
                nm = find_names(m.group(1))
                if nm and nm[0] in pool:
                    return nm[0]
            nm = [x for x in find_names(s) if x in pool]
            if len(nm) == 1:
                return nm[0]
        return None

    for u in units:
        if u["who"] in ("M", "F"):
            t = pron_target(u["i"], u["who"])
            if t:
                u["who"] = t
            else:
                pool = MALE if u["who"] == "M" else FEMALE
                cands = [c for c in block_cast(u["i"]) if c in pool]
                u["who"] = cands[0] if len(cands) == 1 else None
                if u["who"]:
                    u["how"] = "pron-block"

    # ---------------- 呼语 ----------------
    def voc_target(q):
        m = VOC_IN.search(q)
        if m:
            raw = m.group(1)
            return {"Kingshaw": "Charles", "Hooper": "Edmund"}.get(raw, raw)
        if ADULT_ADDR.search(q):
            return "__ADULT__"
        return None

    for u in units:
        if u["who"]:
            continue
        tgt = voc_target(u["text"])
        if not tgt:
            continue
        cands = [c for c in block_cast(u["i"])]
        if tgt == "__ADULT__":
            a = [c for c in cands if c in ADULTS]
            if len(a) == 1:
                u["who"], u["how"] = a[0], "adult-addr"
            continue
        others = [c for c in cands if c != tgt]
        if len(others) == 1:
            u["who"], u["how"] = others[0], "vocative"
        elif len(others) >= 2:
            same_sex = [c for c in others if (c in MALE) == (tgt in MALE)]
            if len(same_sex) == 1:
                u["who"], u["how"] = same_sex[0], "vocative-sex"

    # ---------------- 交替（块内双人） ----------------
    def gap_between(a, b):
        """两单元之间有无叙述插入"""
        if b["seq"] == a["seq"] + 1:
            if a["i"] == b["i"]:
                return not (a["next_narr"] or b["prev_narr"])
            if b["i"] == a["i"] + 1:
                return not (a["next_narr"] or b["prev_narr"])
        return False

    for _ in range(14):
        changed = False
        for k, u in enumerate(units):
            if u["who"]:
                continue
            cands = list(block_cast(u["i"]))
            if len(cands) != 2:
                continue
            for d in (-1, 1):
                kk = k + d
                if not (0 <= kk < len(units)):
                    continue
                v = units[kk]
                if v["who"] not in cands:
                    continue
                ok = gap_between(v, u) if d < 0 else gap_between(u, v)
                if not ok:
                    continue
                other = [c for c in cands if c != v["who"]]
                if len(other) == 1:
                    u["who"], u["how"] = other[0], "alt"
                    changed = True
                    break
        if not changed:
            break

    # ---------------- 块内唯一 ----------------
    for u in units:
        if u["who"]:
            continue
        cands = list(block_cast(u["i"]))
        if len(cands) == 1:
            u["who"], u["how"] = cands[0], "block-uniq"

    # ---------------- 定级 ----------------
    for u in units:
        if not u["who"]:
            u["conf"] = "UNKNOWN"
        elif u["who"] == "__THOUGHT__":
            u["conf"] = "THOUGHT"
        elif u["how"].startswith(("name", "kin", "pron", "vocative", "adult")):
            u["conf"] = "CONFIRMED"
        elif u["how"].startswith("alt"):
            u["conf"] = "ALTERNATE"
        else:
            u["conf"] = "WEAK"

    cc = Counter(u["conf"] for u in units)
    wc = Counter(u["who"] for u in units)
    print("对白单元 %d（v4 段落级 1168）" % len(units))
    for k, v in cc.most_common():
        print("  %-12s %4d  %5.1f%%" % (k, v, 100.0 * v / len(units)))
    print("\n角色：")
    for k, v in wc.most_common():
        print("  %-12s %4d" % (k, v))
    print("\nhow:", Counter(u["how"] for u in units).most_common(14))

    json.dump(dict(units=units, stats=dict(total=len(units), conf=dict(cc), who=dict(wc))),
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % OUT_JSON)


if __name__ == "__main__":
    main()
