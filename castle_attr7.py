# -*- coding: utf-8 -*-
"""
《我是城堡之王》对白归属 v7
============================
v6 人工核对 40 条后的结论（错误率实测，不是估计）：

| how 类别 | 条数 | 抽检对/错 | 问题 |
|---|---|---|---|
| name-weak-prevpara | 142 | 5/3 | 只凭前段出现名字就判，名字常是被提及而非说话人 |
| name-weak-nextpara | 103 | 3/5 | 同上，更差 |
| alt | 193 | 6/2 | 基本可用，但呼语该优先于它 |
| name | 156 | 6/2 | ★ find_names 取「最后一个名字」，而说话人是归属动词的主语 |
| name-after | 88 | 2/1 | 同上 |

★ 核心 bug：`Mrs Helena Kingshaw said, '...'` 被判成 Charles ——
  find_names 返回全段最后一个名字，但主语是紧挨归属动词前面的那个。
  修法：只在**归属动词之前**找名字，取最靠近动词的；动词前没有才看动词后
  （"said Mr Hooper" 这种倒装）。

v7 优先级（强 → 弱）：
  1 同段前置叙述 + 归属动词 + 名字
  2 同段后置叙述 + 归属动词 + 名字
  3 呼语（引号内叫对方名字 → 说话人是块内另一人）
  4 跨段叙述 + 归属动词 + 名字
  5 代词（向前找主语人名）
  6 交替（块内双人 + 两单元之间无叙述）
  7 同段 name-weak
  8 块内唯一角色
  9 UNKNOWN（不猜）

废弃：跨段 name-weak（v6 的 245 条，错误率 >50%）。
"""
import json
import re
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT_JSON = "G:/_setup/castle_dialog_v7.json"
APO = "\x01"

CAST = [
    ("Edmund", ["Edmund", "Hooper", "Master Hooper"]),
    ("Charles", ["Charles", "Kingshaw"]),
    ("Joseph", ["Joseph Hooper", "Mr Hooper", "Joseph"]),
    ("Helena", ["Mrs Kingshaw", "Helena", "Mrs Hooper"]),
    ("Fielding", ["Anthony Fielding", "Fielding", "Anthony"]),
    ("Boland", ["Mrs Boland", "Alice Boland", "Alice"]),
    ("Fenwick", ["Fenwick"]),
    ("Casey", ["Casey"]),
]
ALIAS = sorted([(a, c) for c, al in CAST for a in al], key=lambda x: -len(x[0]))
MALE = {"Edmund", "Charles", "Joseph", "Fielding", "Fenwick", "Casey"}
FEMALE = {"Helena", "Boland"}
KIDS = {"Edmund", "Charles"}
ADULTS = {"Joseph", "Helena", "Fielding", "Boland"}

SPEECH = (r"said|asked|replied|answered|continued|shouted|yelled|muttered|"
          r"responded|added|went on|whispered|cried|repeated|told|began|"
          r"called|screamed|sighed|snapped|murmured|observed|remarked|"
          r"explained|agreed|admitted|protested|insisted|urged|begged|"
          r"ordered|announced|declared|suggested|put in|broke in")
THOUGHT = (r"thought|wondered|decided|felt|knew|remembered|imagined|"
           r"realised|realized|considered|reflected|supposed|hoped|feared|"
           r"wished|planned|recalled|dreamed|dreamt|longed")

ATTR_RE = re.compile(r"\b(?:%s)\b" % SPEECH, re.I)
THOUGHT_RE = re.compile(r"\b(?:%s)\b" % THOUGHT, re.I)
SCENE_SHIFT = re.compile(
    r"\b(next morning|next day|that night|in the morning|in the afternoon|"
    r"the following|hours later|when he woke|afterwards|later that|"
    r"at breakfast|at lunch|at tea|at supper|during the night)\b", re.I)
CHAPTER = re.compile(r"^\s*Chapter\s+\d+", re.I)

VOC_IN = re.compile(r"[,!?]\s*(Hooper|Kingshaw|Charles|Edmund)\s*(?:[.!?,]|$)")
ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)
KIN = [(re.compile(r"\b(his|her|the|my)\s+father\b", re.I), "Joseph"),
       (re.compile(r"\b(his|her|the|my)\s+mother\b", re.I), "Helena")]
# 假设/未发生的引语：等着他来这样说、本会这样说
HYP = re.compile(r"waiting for .{0,40}to (come and )?say|would have said|"
                 r"might have said|could have said|was going to say", re.I)


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
    return [w for rx, w in KIN if rx.search(txt)]


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


def owner_of(narr):
    """从叙述片段取说话人。★ 只在归属动词之前找名字（主语位置）。"""
    if not narr or not narr.strip():
        return None, None
    m = ATTR_RE.search(narr)
    if m:
        before = narr[:m.start()]
        after = narr[m.end():]
        nm = find_names(before)
        if nm:
            return nm[-1], "name"          # 动词前最近的名字 = 主语
        kin = find_kin(before)
        if kin:
            return kin[-1], "kin"
        nm = find_names(after[:40])         # 倒装 "said Mr Hooper"
        if nm:
            return nm[0], "name-inv"
        mm = re.search(r"\b(he|she)\b", before, re.I)
        if mm:
            return ("M" if mm.group(1).lower() == "he" else "F"), "pron"
        mm = re.search(r"\b(he|she)\b", after[:30], re.I)
        if mm:
            return ("M" if mm.group(1).lower() == "he" else "F"), "pron-inv"
        return None, "attr-noname"
    if THOUGHT_RE.search(narr):
        return None, "thought"
    # 无归属动词：只认叙述句首的主语名字（前 15 字符），取最靠前那个
    head = narr.strip()[:15]
    nm = find_names(head)
    if nm:
        return nm[0], "name-weak"
    kin = find_kin(head)
    if kin:
        return kin[0], "kin-weak"
    return None, None


def main():
    paras = load_paras()
    n = len(paras)
    texts = [unapo(p["text"]) for p in paras]
    has_q = [("'" in p["text"]) for p in paras]

    # ---------- 对话块 ----------
    block = [0] * n
    bid, gap = 0, 0
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

    bcount = defaultdict(Counter)
    for i in range(n):
        for c in find_names(paras[i]["text"]) + find_kin(paras[i]["text"]):
            bcount[block[i]][c] += 1

    def block_cast(i):
        """块内主要说话人：频次前 2。第 3 名逼近第 2 名时放弃（可能三人对话）。"""
        c = bcount[block[i]]
        if not c:
            return set()
        top = c.most_common()
        if len(top) == 1:
            return {top[0][0]}
        if len(top) >= 3 and top[2][1] * 2 >= top[1][1]:
            return set()
        return {x for x, _ in top[:2]}

    def local_cast(i, w=4):
        """局部窗口 cast（±w 段），交替判定优先用这个。"""
        s = set()
        for k in range(max(0, i - w), min(n, i + w + 1)):
            s |= set(find_names(paras[k]["text"])) | set(find_kin(paras[k]["text"]))
        return s & (MALE | FEMALE)

    # ---------- 拆单元 ----------
    units = []
    for i in range(n):
        parts = split_units(paras[i]["text"])
        qidx = [k for k, (kind, _) in enumerate(parts) if kind == "quote"]
        for pos, k in enumerate(qidx):
            txt = parts[k][1]
            pn = parts[k - 1][1] if k > 0 and parts[k - 1][0] == "narr" else ""
            nn = parts[k + 1][1] if k + 1 < len(parts) and parts[k + 1][0] == "narr" else ""
            q = unapo(txt).strip()
            if not re.search(r"[A-Za-z]", q):
                continue
            units.append(dict(
                i=i, seq=len(units), text=q, who=None, how="",
                prev_narr=unapo(pn).strip(), next_narr=unapo(nn).strip(),
                in_para_pos=pos, block=block[i],
                hyp=bool(HYP.search(unapo(pn) + " " + unapo(nn)))))
    for u in units:
        u["prev_narr_own"] = u["prev_narr"]

    # ---------- 1/2 同段归属动词 ----------
    for u in units:
        w, how = owner_of(u["prev_narr_own"])
        if w:
            u["who"], u["how"] = w, how
            continue
        w, how = owner_of(u["next_narr"])
        if w:
            u["who"], u["how"] = w, (how or "") + "-after"

    # ---------- 心理独白 ----------
    for u in units:
        if u["who"]:
            continue
        for s in (u["prev_narr_own"], u["next_narr"]):
            if s and THOUGHT_RE.search(s) and not ATTR_RE.search(s):
                u["who"], u["how"] = "__THOUGHT__", "thought"
                break

    # ---------- 3 呼语 ----------
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
        cands = list(block_cast(u["i"]))
        if tgt == "__ADULT__":
            a = [c for c in cands if c in ADULTS]
            if len(a) == 1:
                u["who"], u["how"] = a[0], "adult-addr"
            continue
        others = [c for c in cands if c != tgt]
        if len(others) == 1:
            u["who"], u["how"] = others[0], "vocative"
        elif len(others) >= 2:
            same = [c for c in others if (c in MALE) == (tgt in MALE)]
            if len(same) == 1:
                u["who"], u["how"] = same[0], "vocative-sex"

    # ---------- 4 跨段叙述 + 归属动词 ----------
    def para_narr(j, side):
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
        for j, side, tag in ((u["i"] - 1, "tail", "pp"), (u["i"] + 1, "head", "np")):
            s = para_narr(j, side)
            if not s or len(s) > 240:
                continue
            w, how = owner_of(s)
            if w and w != "__THOUGHT__" and how in ("name", "name-inv", "kin"):
                u["who"], u["how"] = w, "%s-%s" % (how, tag)
                break

    # ---------- 5 代词 ----------
    def pron_target(i, sex):
        pool = MALE if sex == "M" else FEMALE
        for k in range(i - 1, max(-1, i - 8), -1):
            for m in re.finditer(r"(?:^|[.!?]\s+|,\s+)([A-Z][a-z]+)\b", texts[k]):
                nm = find_names(m.group(1))
                if nm and nm[0] in pool:
                    return nm[0]
            nm = [x for x in find_names(texts[k]) if x in pool]
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

    # ---------- 6 交替 ----------
    def gap_between(a, b):
        if b["seq"] == a["seq"] + 1:
            if a["i"] == b["i"]:
                return not (a["next_narr"] or b["prev_narr_own"])
            if b["i"] == a["i"] + 1:
                return not (a["next_narr"] or b["prev_narr_own"])
        return False

    for _ in range(14):
        changed = False
        for k, u in enumerate(units):
            if u["who"]:
                continue
            cands = list(local_cast(u["i"]))
            if len(cands) != 2:
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

    # ---------- 7 同段 name-weak ----------
    for u in units:
        if u["who"]:
            continue
        for s in (u["prev_narr_own"], u["next_narr"]):
            w, how = owner_of(s)
            if w and how in ("name-weak", "kin-weak"):
                u["who"], u["how"] = w, how
                break

    # ---------- 8 块内唯一 ----------
    for u in units:
        if u["who"]:
            continue
        cands = list(block_cast(u["i"]))
        if len(cands) == 1:
            u["who"], u["how"] = cands[0], "block-uniq"

    # ---------- 定级 ----------
    for u in units:
        if not u["who"]:
            u["conf"] = "UNKNOWN"
        elif u["who"] == "__THOUGHT__":
            u["conf"] = "THOUGHT"
        elif u.get("hyp"):
            u["conf"] = "HYPOTHETICAL"
        elif u["how"] in ("name-weak-after", "name-weak"):
            u["conf"] = "WEAK"
        elif u["how"].startswith(("name", "kin", "pron", "vocative", "adult")):
            u["conf"] = "CONFIRMED"
        elif u["how"].startswith("alt"):
            u["conf"] = "ALTERNATE"
        else:
            u["conf"] = "WEAK"
        u.pop("prev_narr_own", None)

    cc = Counter(u["conf"] for u in units)
    wc = Counter(u["who"] for u in units)
    print("对白单元 %d" % len(units))
    for k, v in cc.most_common():
        print("  %-12s %4d  %5.1f%%" % (k, v, 100.0 * v / len(units)))
    print("\n角色：")
    for k, v in wc.most_common():
        print("  %-12s %4d" % (k, v))
    print("\nhow:", Counter(u["how"] for u in units).most_common(16))

    json.dump(dict(units=units, stats=dict(total=len(units), conf=dict(cc), who=dict(wc))),
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % OUT_JSON)


if __name__ == "__main__":
    main()
