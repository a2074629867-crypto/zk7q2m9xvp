# -*- coding: utf-8 -*-
"""从 _book/book.txt 抽出前三章的旁白（非引号部分），切成 TTS 单元。

规则：
- 段落 = 空行分隔的行
- 引号 ‘…’ / “…” 内的算对白，留给角色声线；引号外的算旁白
- 旁白按句切，单句 >28 词再按逗号切（dots.tts 长句必 OOM）
- 记录每个单元后该插多长停顿（逗号 1.17 / 句号 1.76 / 段落 2.50）
"""
import json
import re

SRC = "G:/_setup/_book/book.txt"
OUT = "G:/_setup/mt_plan.json"

C_COMMA, C_PERIOD, C_PARA = 1.17, 1.76, 2.50

raw = open(SRC, encoding="utf-8", errors="replace").read()
raw = re.sub(r"=== ch\d+\.xhtml ===", "\n", raw)
raw = re.sub(r"\n第 \d+ 节\n", "\n", raw)

# 章节边界（正文里的那一次，不是目录）
marks = []
for m in re.finditer(r"Chapter (One|Two|Three|Four)\b", raw):
    marks.append((m.start(), m.group(1)))
# 取最后一次出现作为正文起点
starts = {}
for pos, name in marks:
    starts[name] = pos
body_start = starts["One"]
end = starts["Four"]
text = raw[body_start:end]

chapters = [
    ("ch1", raw[starts["One"]:starts["Two"]]),
    ("ch2", raw[starts["Two"]:starts["Three"]]),
    ("ch3", raw[starts["Three"]:starts["Four"]]),
]

QUOTE = re.compile(r"[‘“][^‘’“”]*[’”]")


def split_units(par):
    """把一段拆成 [(kind, text)]，kind = 'narr' / 'dial'"""
    out, pos = [], 0
    for m in QUOTE.finditer(par):
        pre = par[pos:m.start()]
        if pre.strip():
            out.append(("narr", pre.strip()))
        out.append(("dial", m.group(0)))
        pos = m.end()
    rest = par[pos:]
    if rest.strip():
        out.append(("narr", rest.strip()))
    return out


def sentences(s):
    """按句末标点切，保留标点"""
    parts = re.split(r"(?<=[.!?…])\s+", s)
    return [p.strip() for p in parts if p.strip()]


def chunk(s, maxw=28):
    ws = s.split()
    if len(ws) <= maxw:
        return [s]
    # 按逗号切，再贪心合并
    segs = [x.strip() for x in re.split(r"(?<=[,;:])\s+", s) if x.strip()]
    out, cur = [], ""
    for seg in segs:
        cand = (cur + " " + seg).strip()
        if len(cand.split()) <= maxw:
            cur = cand
        else:
            if cur:
                out.append(cur)
            cur = seg
    if cur:
        out.append(cur)
    return out


plan = []
for ch, t in chapters:
    t = t.split("\n", 1)[1] if "\n" in t else t          # 去掉 "Chapter X" 行
    paras = [p.strip() for p in re.split(r"\n+", t) if p.strip()]
    for pi, par in enumerate(paras):
        last_para = (pi == len(paras) - 1)
        for kind, seg in split_units(par):
            if kind != "narr":
                continue
            seg = re.sub(r"\s+", " ", seg).strip()
            if not re.search(r"[A-Za-z]", seg):
                continue
            for si, sent in enumerate(sentences(seg)):
                for ci, piece in enumerate(chunk(sent)):
                    # 停顿：段落最后一句 → 段落停顿；句末 → 句号；否则逗号
                    if ci < len(chunk(sent)) - 1:
                        pause = C_COMMA
                    elif sent.rstrip().endswith((".", "!", "?", "…")):
                        pause = C_PARA if (last_para and si == len(sentences(seg)) - 1) else C_PERIOD
                    else:
                        pause = C_COMMA
                    plan.append({"id": "M%04d" % (len(plan) + 1), "ch": ch,
                                 "text": piece, "pause": pause})

words = sum(len(p["text"].split()) for p in plan)
print("单元数", len(plan), "旁白词数", words, "预计 %.0f 分钟(170wpm+停顿)" % (words / 170 * 60 / 60 + sum(p["pause"] for p in plan) / 60))
for ch in ("ch1", "ch2", "ch3"):
    sub = [p for p in plan if p["ch"] == ch]
    print("  %s  %d 单元  %d 词" % (ch, len(sub), sum(len(p["text"].split()) for p in sub)))
json.dump(plan, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("写出", OUT)
for p in plan[:6]:
    print("  %s %.1fs | %s" % (p["id"], p["pause"], p["text"]))
