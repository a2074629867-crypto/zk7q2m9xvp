# -*- coding: utf-8 -*-
"""mt_plan2.py —— 从 book.txt 抽取前三章【纯旁白】单元。

源文本是硬换行的（一行不一定是一段），所以先按「行尾是否句末标点 + 下一行是否大写/引号开头」
还原段落，再在段落内剔除 ‘…’ 对白。

规则：
1. 只读旁白；‘…’ 之内的人物对白一个字都不读（留待后面单独配音色）
2. 归属尾巴（his father said, nervously,）属于旁白，保留为独立单元 —— 后面插回对白时位置才对
3. 段落内按句切；单句 >26 词按逗号/分号再切（dots.tts 长句易 OOM）
4. 停顿按马修母带 641 个间隙实测值缩短（用户：间隙短一点）
"""
import json
import re

SRC = "G:/_setup/_book/book.txt"
OUT = "G:/_setup/mt_plan2.json"
BOUNDS = {"ch1": (1805, 18208), "ch2": (18208, 40161), "ch3": (40161, 70725)}

GAP_COMMA = 0.62      # 实测 1.17 → 0.62
GAP_PERIOD = 0.95     # 实测 1.76 → 0.95
GAP_PARA = 1.30       # 实测 2.50 → 1.30
GAP_QUOTE = 0.30      # 对白被跳过处，给一点气口

MAXW = 26
OPEN_Q, CLOSE_Q = "\u2018", "\u2019"


def quote_depth(s):
    """未闭合的 ‘ 数量（’ 后面跟字母时是撇号，不算收尾）。"""
    depth, i = 0, 0
    while i < len(s):
        if s[i] == OPEN_Q:
            depth += 1
        elif s[i] == CLOSE_Q:
            nxt = s[i + 1] if i + 1 < len(s) else " "
            if not nxt.isalpha() and depth > 0:
                depth -= 1
        i += 1
    return depth


def paragraphs(body):
    """还原段落：硬换行的续行并入同一段；对白未闭合时绝不切段。"""
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    groups, cur = [], []
    for i, ln in enumerate(lines):
        cur.append(ln)
        if i == len(lines) - 1:
            break
        nxt = lines[i + 1]
        ends_sent = bool(re.search(r"[.!?\u2026][\u2019\u201d]?$", ln))
        starts_new = bool(re.match(r"[\u2018\u201cA-Z]", nxt))
        if ends_sent and starts_new and quote_depth(" ".join(cur)) == 0:
            groups.append(" ".join(cur))
            cur = []
    if cur:
        groups.append(" ".join(cur))
    return groups


def strip_dialogue(par):
    """去掉 ‘…’ 对白。’ 兼作撇号，收尾引号后面一定不是字母。"""
    # 源文有笔误：用 ’ 当开引号（"His father said, ’You will come…"），先归一
    par = re.sub(r"(?<=[\s,;:])\u2019(?=[A-Z])", OPEN_Q, par)
    out, i, n = [], 0, len(par)
    while i < n:
        if par[i] == OPEN_Q:
            j = par.find(CLOSE_Q, i + 1)
            while j != -1:
                nxt = par[j + 1] if j + 1 < n else " "
                if not nxt.isalpha():
                    break
                j = par.find(CLOSE_Q, j + 1)
            if j == -1:                     # 没有收尾引号：只去掉开引号，文本不丢
                i += 1
                continue
            out.append(" \u0001 ")
            i = j + 1
            continue
        out.append(par[i])
        i += 1
    return "".join(out)


def sentences(s):
    s = re.sub(r"\s+", " ", s).strip()
    return [p.strip() for p in re.split(r"(?<=[.!?\u2026])\s+", s)
            if p.strip() and re.search(r"[A-Za-z]", p)]


def chunk(sent):
    if len(sent.split()) <= MAXW:
        return [sent]
    segs = [x.strip() for x in re.split(r"(?<=[,;:])\s+", sent) if x.strip()]
    out, cur = [], ""
    for seg in segs:
        cand = (cur + " " + seg).strip()
        if len(cand.split()) <= MAXW:
            cur = cand
        else:
            if cur:
                out.append(cur)
            w = seg.split()
            while len(w) > MAXW:
                out.append(" ".join(w[:MAXW]))
                w = w[MAXW:]
            cur = " ".join(w)
    if cur:
        out.append(cur)
    return out


def para_units(par):
    clean = strip_dialogue(par)
    frags = clean.split("\u0001")           # 片段之间 = 有一段对白被跳过
    units = []
    for fi, frag in enumerate(frags):
        for sent in sentences(frag):
            for piece in chunk(sent):
                units.append([piece, None])
        if fi < len(frags) - 1 and units:
            units[-1][1] = GAP_QUOTE        # 后面紧跟被跳过的对白
    return units


def is_quote_residue(t):
    """真残留：还有 ‘ ，或 ’ 后面不是字母（撇号不算）。"""
    if OPEN_Q in t:
        return True
    for i, c in enumerate(t):
        if c == CLOSE_Q:
            nxt = t[i + 1] if i + 1 < len(t) else " "
            if not nxt.isalpha():
                return True
    return False


def main():
    raw = open(SRC, encoding="utf-8", errors="replace").read()
    plan, stat, leak = [], {}, []
    for ch, (a, b) in BOUNDS.items():
        body = raw[a:b]
        body = re.sub(r"^Chapter \w+\s*", "", body)
        for par in paragraphs(body):
            units = para_units(par)
            for ui, (text, gq) in enumerate(units):
                if gq is not None:
                    gap = gq
                elif ui == len(units) - 1:
                    gap = GAP_PARA
                elif re.search(r"[.!?\u2026]$", text):
                    gap = GAP_PERIOD
                else:
                    gap = GAP_COMMA
                if is_quote_residue(text):
                    leak.append(text)
                plan.append({"id": "N%04d" % (len(plan) + 1), "ch": ch,
                             "text": text, "gap": gap})
        stat[ch] = sum(1 for p in plan if p["ch"] == ch)
    json.dump(plan, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    words = sum(len(p["text"].split()) for p in plan)
    gaps = sum(p["gap"] for p in plan)
    print("单元 %d  旁白词数 %d  停顿合计 %.1f 分钟" % (len(plan), words, gaps / 60))
    for ch, n in stat.items():
        sub = [p for p in plan if p["ch"] == ch]
        print("  %s %4d 单元  %5d 词" % (ch, n, sum(len(p["text"].split()) for p in sub)))
    print("含引号残留 %d 条" % len(leak))
    for t in leak[:5]:
        print("   !", t[:80])
    print("--- 前 10 条 ---")
    for p in plan[:10]:
        print("  %s %.2fs | %s" % (p["id"], p["gap"], p["text"]))


if __name__ == "__main__":
    main()
