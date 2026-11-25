"""句内停顿审计：把「听感断开」变成可量化的数

用户口径：「所有语句都没有分割好，都是从中间断开的」。

前面用「数字零」去找，结果零全在句尾（前导/尾随静音），句中不是零。
真正的断是**词间停顿过长**：

    真实对白   逗号 200~350ms   句号 350~600ms   省略号/破折号 400~800ms
    模型生成   逗号能到 800ms   句号能到 1000ms  ← 听感上就是「断成两截」

判据用「相邻词间隙」而不是「静音检测」，因为只有词边界知道停顿属于哪个标点。
用 ensemble 上限（先按对白经验值，跑完一批再按实测 P90 校准）。
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 按 239 条实测 p90 校准（都不超过真实对白上限）：
#   none     p90 120  p99 1040  → 150（无标点不该有停顿，但模型天生留换气口）
#   comma    p90 580           → 420（真实逗号 200~350）
#   dash     p90 426           → 750（破折号本来要停）
#   period   p90 950  p99 2955 → 700（真实句号 400~600）
#   ellipsis p90 1580          → 1000（省略号要留长，但不能到 1.5s）
#   stutter  —— 同一词重复（I – I / he – he）**不是停顿**，是口吃；
#              用户口径 2026-11-25 08:45：「如果是口吃，间隔就不长，它不是停顿，只是口吃。」
#              真实口吃重复间隔 0~200ms，所以单独一档，不许套 dash 的 750。
LIMITS = {"period": 700, "ellipsis": 1000, "comma": 420, "dash": 750,
          "none": 150, "stutter": 200}
MARK = re.compile(r"(\.\.\.|\u2026|\u2014|\u2013|--|[,;:]|\.(?!\.))")


def gap_kind(spans, marks, i):
    """间隙类型。★ 同一词重复优先判口吃，不再看标点。

    用户 2026-11-25：「s46……前面 I 与 I 之间间隔不用太大，说 I 差 0 点，
    最多 0.2 秒之后就可以接下来下一个 I。」「如果是口吃，间隔就不长，它不是停顿。」
    """
    def _w(s):
        return (s or "").strip("'’.").lower()
    if i + 1 < len(spans) and _w(spans[i][0]) and _w(spans[i][0]) == _w(spans[i + 1][0]):
        return "stutter"
    return marks[i][1] if i < len(marks) else "none"
MARK = re.compile(r"(\.\.\.|\u2026|\u2014|\u2013|--|[,;:]|\.(?!\.))")


def clean(t):
    t = (t or "").strip()
    if t and t[0] in "\u2018\u201c\"'":
        t = t[1:]
    if t and t[-1] in "\u2019\u201d\"'":
        t = t[:-1]
    return t.replace("\u2019", "'").replace("\u2018", "'")


def word_mark_map(text):
    """给每个词标上「它后面跟的标点类型」。返回 [(word, kind), ...]。"""
    out, pos = [], 0
    for m in MARK.finditer(text):
        ws = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text[pos:m.start()])
        mk = m.group()
        if mk in ("...", "\u2026"):
            kind = "ellipsis"
        elif mk in ("\u2014", "\u2013", "--") or mk.strip() == "-":
            kind = "dash"
        elif mk in (",", ";", ":"):
            kind = "comma"
        else:
            kind = "period"
        for i, w in enumerate(ws):
            out.append((w.lower(), kind if i == len(ws) - 1 else "none"))
        pos = m.end()
    for w in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text[pos:]):
        out.append((w.lower(), "none"))
    return out


def align_spans(path, text, proc, model):
    """返回 [(word, start, end)]，缩写碎片（IT + S）合并。"""
    import _align_gate as AG
    r = AG.align(proc, model, path, text)
    if not r:
        return None
    ws, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if cur:
                ws.append(cur)
                cur = []
        else:
            cur.append(tk)
    if cur:
        ws.append(cur)

    spans = []
    for w in ws:
        s = "".join(x["tok"] for x in w).lower()
        st, en = w[0]["start"] * 0.02, w[-1]["end"] * 0.02
        # 单字母碎片接在上一个词后面（It's 被切成 IT + S）
        if spans and len(s) == 1 and s.isalpha() and s not in ("i", "a"):
            spans[-1] = (spans[-1][0] + s, spans[-1][1], en)
        else:
            spans.append((s, st, en))
    return spans


def audit(rid, path, text, proc, model):
    spans = align_spans(path, text, proc, model)
    if not spans:
        return None
    marks = word_mark_map(text)
    # 词数与标点映射数不一致时按较短的走（对齐可能丢词）
    n = min(len(spans) - 1, len(marks))
    gaps = []
    for i in range(n):
        w0, s0, e0 = spans[i]
        w1, s1, e1 = spans[i + 1]
        ms = (s1 - e0) * 1000
        kind = gap_kind(spans, marks, i)
        gaps.append(dict(after=w0, before=w1, ms=round(ms), kind=kind,
                         limit=LIMITS[kind], over=ms > LIMITS[kind]))
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / sr
    tot = sum(g["ms"] for g in gaps)
    worst = max(gaps, key=lambda x: x["ms"]) if gaps else None
    return dict(id=rid, dur=round(dur, 2), nword=len(spans), gaps=gaps,
                over=[g for g in gaps if g["over"]],
                pause_total=tot, pause_ratio=round(tot / 1000 / dur, 3),
                worst=worst, text=text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--seed", type=int, default=0, help=">0 读 _seedpick/<id>/s<seed>.wav")
    ap.add_argument("--json", default="")
    ap.add_argument("--all", action="store_true", help="扫全库 239 条")
    a = ap.parse_args()

    import _align_gate as AG
    proc, model = AG.load_model()
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    ids = sorted(rows) if a.all else [x.strip() for x in a.ids.split(",") if x.strip()]

    out = {}
    for rid in ids:
        text = clean(rows[rid]["text"])
        p = (os.path.join("G:/_setup/_seedpick", rid, "s%d.wav" % a.seed) if a.seed
             else os.path.join(a.dir, rid + ".wav"))
        if not os.path.exists(p):
            continue
        r = audit(rid, p, text, proc, model)
        if not r:
            print("%-9s 对齐失败" % rid)
            continue
        out[rid] = r
        w = r["worst"]
        print("%-9s %5.2fs 停顿%4.0fms(%2.0f%%) 间隙%2d 超限%2d 最长 %4dms(%s)" % (
            rid, r["dur"], r["pause_total"], 100 * r["pause_ratio"],
            len(r["gaps"]), len(r["over"]), w["ms"] if w else 0, w["kind"] if w else "-"))
        for g in r["over"][:4]:
            print("      %s→%s %4dms %s 限%d 超%d" % (
                g["after"], g["before"], g["ms"], g["kind"], g["limit"], g["ms"] - g["limit"]))

    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.json)
    if out:
        ov = sum(1 for v in out.values() if v["over"])
        print("\n%d 条中 %d 条有超限停顿（%.0f%%）" % (len(out), ov, 100 * ov / len(out)))


if __name__ == "__main__":
    sys.exit(main())
