"""从 EPUB 提取的英文原文 - 切句 - 产出 lines.jsonl（前三章）

链路：PDF 转 EPUB 的硬换行 → unwrap 接回段落 → 剥章节标题 → 按句切 → 标注对白
红线：一句话 = 一个生成单元，不再二次拆分。
"""
import json
import re
from collections import Counter

from text_unwrap import unwrap

SRC = r"G:/_setup/_castle_en_full.txt"
OUT = r"G:/_setup/_castle_en_ch123.jsonl"

CH = {"Chapter One": (9, 147, 1), "Chapter Two": (147, 380, 2), "Chapter Three": (380, 631, 3)}

ABBR = {"Mr", "Mrs", "Miss", "Dr", "St", "Jr", "Sr", "No", "vs", "etc"}


def clean(p: str) -> str:
    p = p.replace("\u00ad", "")
    p = re.sub(r"\s+", " ", p).strip()
    return p


def split_sentences(para: str):
    out, buf, i, n = [], "", 0, len(para)
    while i < n:
        ch = para[i]
        buf += ch
        if ch in ".!?":
            j = i + 1
            while j < n and para[j] in "’'\"”)":
                buf += para[j]
                j += 1
            is_end = j >= n or para[j] == " "
            if ch == ".":
                tail = re.search(r"([A-Za-z.]+)$", buf[:-1])
                word = tail.group(1) if tail else ""
                if word in ABBR or (len(word) == 1 and word.isupper()):
                    is_end = False
            if is_end:
                out.append(buf.strip())
                buf, i = "", j
                continue
            i = j
            continue
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return out


def wc(s):
    return len(re.findall(r"[A-Za-z0-9’'-]+", s))


def split_long(s, limit=45):
    if wc(s) <= limit:
        return [s]
    parts = [p.strip() for p in re.split(r"(?<=[;:])\s+|\s+[—–]\s+", s) if p.strip()]
    if len(parts) < 2:
        commas = [m.start() for m in re.finditer(r",\s", s)]
        if not commas:
            return [s]
        mid = len(s) / 2
        cut = min(commas, key=lambda x: abs(x - mid))
        return [s[:cut + 1].strip(), s[cut + 1:].strip()]
    res, cur = [], ""
    for p in parts:
        cand = (cur + " " + p).strip()
        if wc(cand) > limit and cur:
            res.append(cur)
            cur = p
        else:
            cur = cand
    if cur:
        res.append(cur)
    return res


def split_adjacent_quotes(sents):
    """‘A’ ‘B’ —— 两段对白紧邻、中间没有句末标点，必须拆成两条（说话人不同）。"""
    out = []
    for s in sents:
        for piece in re.split(r"(?<=[’”])\s+(?=[‘“])", s):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def quote_net(s: str) -> int:
    """引号配平度。>0 表示还在一段引号内（未闭合），不能在此断句。"""
    left = s.count("‘") + s.count("“")
    right = s.count("’") + s.count("”")
    right -= len(re.findall(r"(?<=[A-Za-z])’(?=[A-Za-z])", s))   # 撇号不算右引号
    return left - right


def merge_quotes(sents):
    """同一个引号块内的多句合并成一个生成单元（拆开 = 两次表演，毁整句弧线）。"""
    out = []
    buf = ""
    for s in sents:
        buf = (buf + " " + s).strip() if buf else s
        if quote_net(buf) <= 0:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def merge_short(sents, min_w=4):
    """过短碎片并入相邻句 —— 单独生成 2 词句会缺上下文、语气飘。"""
    out = []
    for s in sents:
        if not out:
            out.append(s)
        elif wc(s) < min_w or wc(out[-1]) < min_w:
            out[-1] = out[-1] + " " + s
        else:
            out.append(s)
    return out


all_lines = open(SRC, encoding="utf-8").read().split("\n")

records, idx = [], 0
for name, (a, b, num) in CH.items():
    body = all_lines[a:b]
    paras = unwrap(body)
    paras[0] = re.sub(r"^Chapter\s+(One|Two|Three)\s+", "", paras[0])
    for pi, raw in enumerate(paras):
        p = clean(raw)
        if len(p) < 2:
            continue
        sents = merge_short(merge_quotes(split_adjacent_quotes(split_sentences(p))))
        pieces = []
        for s in sents:
            pieces.extend(split_long(s))
        for k, s in enumerate(pieces):
            s = s.strip()
            if not s:
                continue
            idx += 1
            records.append({
                "id": "c%d_%04d" % (num, idx),
                "idx": idx,
                "chapter": name,
                "para": pi,
                "part": k,
                "text": s,
                "words": wc(s),
                "dialog": bool(re.match(r"^[‘'\"“]", s)),
                "speaker": None,
            })

with open(OUT, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

tot_w = sum(r["words"] for r in records)
dlg = sum(1 for r in records if r["dialog"])
print("TOTAL lines:", len(records))
print("  dialog:", dlg, " narration:", len(records) - dlg)
print("words:", tot_w, " avg %.1f" % (tot_w / len(records)))
print("by chapter:", dict(Counter(r["chapter"] for r in records)))
L = sorted(r["words"] for r in records)
print("words p50/p90/p99/max: %d/%d/%d/%d" % (L[len(L) // 2], L[int(len(L) * .9)], L[int(len(L) * .99)], L[-1]))
print("over45:", sum(1 for r in records if r["words"] > 45), " under3:", sum(1 for r in records if r["words"] < 3))
print("\n--- 前 8 条 ---")
for r in records[:8]:
    print("  %-9s %2d  %s" % (r["id"], r["words"], r["text"][:88]))
print("\n--- 中段 8 条 ---")
mid = len(records) // 2
for r in records[mid:mid + 8]:
    print("  %-9s %2d  %s" % (r["id"], r["words"], r["text"][:88]))
