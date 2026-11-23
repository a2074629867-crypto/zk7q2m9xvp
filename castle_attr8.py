# -*- coding: utf-8 -*-
"""
《我是城堡之王》对白归属 v8
============================
v7 人工核对 18 条 CONFIRMED + ALTERNATE，只有 55~62% 正确 —— 不能交付。
逐条查错，根因是四类，全部是**切分层**的问题，不是归属算法的问题：

1. ★★ **跨段合并判断错误**（最致命）
   v5-v7 用「段落引号数为奇数就与下一段合并」。但 `...things were.'` 的引号是
   **闭引号**（上一段开引号在更早），不是开引号。一合并就把后续 5 句对白全吞进一段，
   split_units 彻底错乱（实测 [766]：10 个引号切成 quote(' ') / narr('You can't...') 交替）。
   → 改为**全文状态机扫描**：从文件头开始维护「是否在引号内」，正确配对跨段引号。

2. **段内多句分属不同人**（[2407]）
   `'You don't frighten me, Hooper...' 'You wait, Kingshaw. That's what.'`
   第一句 Charles，第二句 Edmund。v7 整段判 Edmund，第一句错。
   → 段内每个 quote 独立判定，呼语各自生效。

3. **跨段 name 归属太激进**（[764]）
   `'Yes, but I didn't....'` 后一段是 `Hooper sighed. 'You're stupid...'`，
   Hooper 是下一句的说话人，不是本句。v7 判 Edmund，错。
   → 跨段只在「该段唯一的 quote 且叙述紧贴」时才用，且要求叙述里有明确归属动词。

4. **代词解析不可靠**（[2759]）
   `Fielding jumped back... 'We'll go to my place,' he said` —— he 指 Fielding，
   但 v7 向前找最近的男性名字，找到 Hooper。→ 改为**优先取同段内最近的名词主语**，
   找不到才跨段；跨段仍不唯一则放弃。

另：配角 Fenwick / Casey 已补进角色表（[2169] 因缺 Fenwick 判成 Charles）。
"""
import json
import re
from collections import Counter, defaultdict

SRC = "G:/_setup/castle_full.txt"
OUT_JSON = "G:/_setup/castle_dialog_v8.json"
APO = "\x01"

CAST = [
    ("Edmund", ["Edmund", "Hooper", "Master Hooper"]),
    ("Charles", ["Charles", "Kingshaw"]),
    ("Joseph", ["Joseph Hooper", "Mr Joseph Hooper", "Mr Hooper", "Joseph"]),
    ("Helena", ["Mrs Helena Kingshaw", "Mrs Kingshaw", "Helena"]),
    ("Fielding", ["Anthony Fielding", "Fielding", "Anthony"]),
    ("Boland", ["Mrs Alice Boland", "Mrs Boland", "Alice Boland", "Alice"]),
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

VOC_IN = re.compile(r"[,!?]\s*(Hooper|Kingshaw|Charles|Edmund)\s*(?:[.!?,]|$)|"
                    r"\b(?:Scaredy|stupid|silly|old|poor|little|dear)\s+(Hooper|Kingshaw)\b", re.I)
ADULT_ADDR = re.compile(r"\b(darling|dear|my boy|my dear|sweetheart)\b", re.I)
KIN = [(re.compile(r"\b(his|her|the|my)\s+father\b", re.I), "Joseph"),
       (re.compile(r"\b(his|her|the|my)\s+mother\b", re.I), "Helena")]
HYP = re.compile(r"waiting for .{0,40}to (come and )?say|would have said|"
                 r"might have said|could have said|was going to say", re.I)


def protect_apos(t):
    t = re.sub(r"([A-Za-z])'(?=[A-Za-z])", lambda m: m.group(1) + APO, t)
    t = re.sub(r"([A-Za-z]s)'(?=\s+[a-z])", lambda m: m.group(1) + APO, t)
    return t


def unapo(s):
    return s.replace(APO, "'")


def load_text():
    return protect_apos(open(SRC, encoding="utf-8").read())


def scan_quotes(t):
    """★ 全文状态机：从文件头维护「是否在引号内」，正确配对跨段引号。
    返回 [(start, end)]，end 指向闭合引号的位置。"""
    out, i, n = [], 0, len(t)
    open_at = None
    while i < n:
        c = t[i]
        if c != "'":
            i += 1
            continue
        prev = t[i - 1] if i > 0 else ""
        nxt = t[i + 1] if i + 1 < n else ""
        if prev.isalpha() and nxt.isalpha():          # don't / I've
            i += 1
            continue
        if prev == "s" and (nxt.isspace() or nxt == "") and i + 2 < n and t[i + 2].islower():
            i += 1                                    # spiders' webs
            continue
        if open_at is None:
            open_at = i
        else:
            out.append((open_at, i))
            open_at = None
        i += 1
    return out


def build_paras(t):
    """段落 = 连续非空行块。返回 [(start, end, text)]"""
    out = []
    for m in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", t):
        s, e = m.start(), m.end()
        if not m.group().strip():
            continue
        out.append((s, e, m.group()))
    return out


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


def first_sentence(s):
    """取第一句（到 .!? 为止，且不是缩写点）"""
    m = re.search(r"[.!?](?=\s|$)", s)
    return s[:m.end()] if m else s


def owner_of(narr, after=False):
    """从叙述取说话人。只认归属动词前的名字（主语位）。
    after=True 表示这是引号后的叙述：只认第一句 —— 后面句子里的
    `X said` 属于下一段对白，不能算本句归属（实测 [2534] 因此判反）。"""
    if not narr or not narr.strip():
        return None, None
    if after:
        narr = first_sentence(narr)
    m = ATTR_RE.search(narr)
    if m:
        before, after = narr[:m.start()], narr[m.end():]
        nm = find_names(before)
        if nm:
            return nm[-1], "name"
        kin = find_kin(before)
        if kin:
            return kin[-1], "kin"
        inv = re.match(r"\s*(?:%s)\s+([A-Z][a-z]+)" % SPEECH, after)
        if inv and not re.match(r"\s*(?:to|at|with|for)\b", after.strip()[len(inv.group(0).split()[0]):]):
            nm = find_names(inv.group(1))
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
    head = narr.strip()[:16]
    nm = find_names(head)
    if nm:
        return nm[0], "name-weak"
    kin = find_kin(head)
    if kin:
        return kin[0], "kin-weak"
    return None, None


def main():
    t = load_text()
    paras = build_paras(t)
    n = len(paras)
    ptext = [unapo(p[2]) for p in paras]
    pstart = [p[0] for p in paras]
    pend = [p[1] for p in paras]

    def para_of(pos):
        for i in range(n):
            if pstart[i] <= pos < pend[i]:
                return i
        return n - 1

    quotes = scan_quotes(t)
    print("引号块 %d（全文状态机配对）" % len(quotes))

    # ---------- 每个引号块 = 一个对白单元 ----------
    units = []
    for k, (a, b) in enumerate(quotes):
        pi = para_of(a)
        q = unapo(t[a + 1:b]).strip()
        if not re.search(r"[A-Za-z]", q):
            continue
        # 前置叙述：上一个块结束（或本段开头）→ 本块开始
        prev_end = quotes[k - 1][1] + 1 if k > 0 else pstart[pi]
        pn = unapo(t[max(prev_end, pstart[pi]):a]).strip() if prev_end <= a else ""
        # 后置叙述：本块结束 → 下一个块开始（或本段结束）
        next_start = quotes[k + 1][0] if k + 1 < len(quotes) else pend[pi]
        nn = unapo(t[b + 1:min(next_start, pend[pi])]).strip() if b + 1 <= next_start else ""
        units.append(dict(i=pi, seq=len(units), text=q, who=None, how="",
                          prev_narr=pn, next_narr=nn,
                          start=a, end=b,
                          hyp=bool(HYP.search(pn + " " + nn))))
    print("对白单元 %d" % len(units))

    # ---------- 对话块 ----------
    has_q = [False] * n
    for u in units:
        has_q[u["i"]] = True
    block = [0] * n
    bid, gap = 0, 0
    for i in range(n):
        if CHAPTER.match(ptext[i]) or SCENE_SHIFT.search(ptext[i][:80]):
            bid += 1
            gap = 0
            block[i] = bid
            continue
        if not has_q[i] and len(ptext[i]) > 200:
            gap += 1
            if gap >= 2:
                bid += 1
                gap = 0
        elif has_q[i]:
            gap = 0
        block[i] = bid
    for u in units:
        u["block"] = block[u["i"]]

    bcount = defaultdict(Counter)
    for i in range(n):
        for c in find_names(paras[i][2]) + find_kin(paras[i][2]):
            bcount[block[i]][c] += 1

    def block_cast(i):
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
        s = set()
        for k in range(max(0, i - w), min(n, i + w + 1)):
            s |= set(find_names(paras[k][2])) | set(find_kin(paras[k][2]))
        return s & (MALE | FEMALE)

    # ---------- 1/2 同段归属 ----------
    for u in units:
        w, how = owner_of(u["prev_narr"])
        if w:
            u["who"], u["how"] = w, how
            continue
        w, how = owner_of(u["next_narr"], after=True)
        if w:
            u["who"], u["how"] = w, (how or "") + "-after"

    # ---------- 心理独白 ----------
    for u in units:
        if u["who"]:
            continue
        for s in (u["prev_narr"], u["next_narr"]):
            if s and THOUGHT_RE.search(s) and not ATTR_RE.search(s):
                u["who"], u["how"] = "__THOUGHT__", "thought"
                break

    # ---------- 呼语（段内每个 quote 各自生效）----------
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
        cands = list(local_cast(u["i"], 6))
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

    # ---------- 3 跨段归属（只在紧邻段唯一 quote 时）----------
    def para_narr(j, side):
        if not (0 <= j < n):
            return ""
        # 该段内的引号块
        qs = [(a, b) for a, b in quotes if pstart[j] <= a < pend[j]]
        if not qs:
            return ""
        if side == "tail":
            return unapo(t[qs[-1][1] + 1:pend[j]]).strip()
        return unapo(t[pstart[j]:qs[0][0]]).strip()

    # ★ 跨段归属已废弃：实测 [1521]/[2534] 均判反 ——
    #   前段尾部的 `Hooper said` 归属的是前段引语，不是本段。
    #   没有同段锚点的单元一律留给对话轮次交替或 UNKNOWN。

    # ---------- 4 代词（优先同段名词主语）----------
    def pron_target(u, sex):
        pool = MALE if sex == "M" else FEMALE
        i = u["i"]
        # 同段内本块之前的叙述
        seg = u["prev_narr"]
        # "Fielding's father said" -> 说话人是父亲，不是 Fielding
        seg = re.sub(r"([A-Z][a-z]+)'s (father|mother)\b", r"\2", seg)
        for m in reversed(list(re.finditer(r"(?:^|[.!?]\s+|,\s+)([A-Z][a-z]+)\b", seg))):
            nm = find_names(m.group(1))
            if nm and nm[0] in pool:
                return nm[0]
        # 向前找叙述段（不含引号），优先
        for k in range(i - 1, max(-1, i - 7), -1):
            if "'" in paras[k][2]:
                continue
            nm = [x for x in find_names(ptext[k]) if x in pool]
            if len(nm) == 1:
                return nm[0]
        for k in range(i - 1, max(-1, i - 7), -1):
            nm = [x for x in find_names(ptext[k]) if x in pool]
            if len(nm) == 1:
                return nm[0]
        return None

    for u in units:
        if u["who"] in ("M", "F"):
            t2 = pron_target(u, u["who"])
            if t2:
                u["who"] = t2
            else:
                u["who"] = None

    # ---------- 4.5 跨段引语继承 ----------
    # 原著写法：同一人连续说话跨段时，中间段不加开引号，且前一段不以句末标点收尾。
    # 例：'...as well as someone to look after us in this house.  ← 无句号
    #      Something is soon to be done.'                        ← 同一人继续
    # 必须先于交替执行，否则交替会把「同一人继续说」判成换人（实测 ch1 的
    # 'You had better not go into the Red Room...' 因此判反）。
    for _ in range(4):
        ch2 = False
        for u in units:
            if u["who"] or u["seq"] == 0:
                continue
            prev = units[u["seq"] - 1]
            if not prev["who"] or prev["who"] == "__THOUGHT__":
                continue
            tail = prev["text"].rstrip()
            if tail and tail[-1] not in ".!?\u2026":
                u["who"], u["how"] = prev["who"], "cont"
                ch2 = True
        if not ch2:
            break

    # ---------- 5 对话轮次交替（run 级）----------
    # run = 连续 quote 单元，两单元之间没有叙述
    def no_narr(a, b):
        return not (a["next_narr"] or b["prev_narr"])

    runs, cur = [], [0]
    for k in range(1, len(units)):
        if no_narr(units[k - 1], units[k]):
            cur.append(k)
        else:
            runs.append(cur)
            cur = [k]
    runs.append(cur)

    def run_cast(run, pad=2):
        s2 = set()
        i0 = units[run[0]]["i"]
        i1 = units[run[-1]]["i"]
        for k in range(max(0, i0 - pad), min(n, i1 + pad + 1)):
            s2 |= set(find_names(paras[k][2])) | set(find_kin(paras[k][2]))
        return s2 & (MALE | FEMALE)

    for _ in range(12):
        changed = False
        for run in runs:
            known = [(k, units[k]["who"]) for k in run if units[k]["who"]]
            if not known:
                continue
            rc = run_cast(run)
            for k in run:
                u = units[k]
                if u["who"]:
                    continue
                cands = list(rc) if len(rc) == 2 else (
                    list(local_cast(u["i"])) or list(block_cast(u["i"])))
                if len(cands) != 2:
                    continue
                # 找 run 内最近的已知单元，按距离奇偶交替
                near = min(known, key=lambda x: abs(x[0] - k))
                other = [c for c in cands if c != near[1]]
                if len(other) != 1:
                    continue
                steps = abs(k - near[0])
                u["who"] = near[1] if steps % 2 == 0 else other[0]
                u["how"] = "alt%d" % steps
                changed = True
            known = [(k, units[k]["who"]) for k in run if units[k]["who"]]
        if not changed:
            break

    # ---------- 6 块内唯一 ----------
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
        elif u["how"] in ("name-weak", "name-weak-after"):
            u["conf"] = "WEAK"
        elif u["how"].startswith(("name", "kin", "vocative", "adult")):
            u["conf"] = "CONFIRMED"
        elif u["how"].startswith("pron"):
            u["conf"] = "CONFIRMED"
        elif u["how"].startswith("alt"):
            u["conf"] = "ALTERNATE"
        else:
            u["conf"] = "WEAK"

    cc = Counter(u["conf"] for u in units)
    wc = Counter(u["who"] for u in units)
    print()
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
