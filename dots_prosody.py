#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dots_prosody.py — 文本 → dots.edit 韵律指令编译器（v2：按文字内容决策）

不是套模板：先做文本分析，再按每个子句的语言学特征逐条决定 rate / pause / pitch。

分析维度（全部来自文本本身）
  ① 句法位置   段首句 / 段末句 / 句内第几个子句
  ② 子句长度   词数 → 目标时长（真人短句拖长、长句赶）
  ③ 标点层级   逗号 / 分号 / 冒号 / 破折号 / 句号 / 问号 / 感叹号
  ④ 枚举结构   连续逗号且末项收尾 → 每项等距、末项前蓄势
  ⑤ 句首连接词 and / but / so / then / because / when → 呼吸点
  ⑥ 句子类型   陈述 / 疑问 / 感叹 / 引号内对话
  ⑦ 强调词     全大写 / *斜体* / 数字 → 单独成 span 放慢
  ⑧ 长句呼吸   >=12 词的子句后加一次换气

所有系数都来自实测：
  · 真人锚点 real_trim.wav（29.41s / 38 词）：语音 17.45s、静音 11.96s、间隙中位 1.28s
  · dots 基线 F0_plain.wav（20.80s / 38 词）：语音 14.24s、静音 6.56s、间隙中位 0.60s
  · rate 兑现率 k=0.58：语音时长 = base / (1 - k*(1-r))（拟合 5 个实测点）
  · 词位时长模板 route_a/dur_template.json（653 词）：首 1.30 / 中 1.00 / 逗前 1.25 / 末 1.775
  · 停顿库 pause_bank.json：逗号 1.16s(n=220) / 句号 1.56s(n=142)

用法
  python dots_prosody.py --in text.txt --mode mc --explain
  python dots_prosody.py --in text.txt --mode flat --out tagged.txt
  python dots_prosody.py --in text.txt --mode mc --target-wpm 150 --pause-scale 1.3
  cat text.txt | python dots_prosody.py --stdin --mode mc

模式
  bare  只插停顿（对照）
  flat  全段统一 rate + 分档停顿（最稳）
  mc    完整文本驱动：长度/位置/枚举/连接词/类型/强调 全部参与
"""
import argparse
import json
import os
import re
import sys

# ★ python310._pth 会让脚本目录不进 sys.path，必须显式加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dots_markup as MK   # 官方标记规范：格式转换 + 校验 + 常量

# ---------------------------------------------------------------- 实测常量

RATE_K = 0.58                 # 模型只兑现 58% 的减速
BASE_SPEECH = 14.24           # rate 1.00 时 38 词的语音时长
BASE_WORDS = 38
BASE_GAP = 0.60               # rate 1.00 时间隙中位
REAL_TOTAL = 29.41
REAL_SPEECH = 17.45
REAL_WPM = BASE_WORDS / REAL_SPEECH * 60      # ≈ 131

W_FIRST, W_MID, W_PRECOMMA, W_LAST = 1.30, 1.00, 1.25, 1.775

PAUSE_TARGET = {
    ".": 1.56, "!": 1.45, "?": 1.35,
    ",": 1.16, ";": 1.35, ":": 1.20, "—": 0.95, "–": 0.95, "-": 0.90, "…": 1.40,
}
PAUSE_STEP = {1: 0.10, 2: 0.20, 3: 0.30}
PAUSE_MAX_STACK = 1    # ★实测：连续叠 2 个以上 <pause/> 会导致整段跳词（12.80s / 38 词）

CONNECTIVES = {"and", "but", "so", "then", "because", "when", "while", "until",
               "before", "after", "as", "if", "though", "although", "yet", "or"}
STOPWORDS = set("""a an the and or but if so of to in on at for with from by as is are was
were be been being it its this that these those he she they we you i his her their our your
my me him them us not no do does did have has had will would can could should may might
just then than there here what which who whom when where why how""".split())


def clause_len_mult(n_words):
    n = max(1, n_words)
    raw = (n + (W_FIRST + W_LAST - 2 * W_MID)) / n
    return raw / ((6 + (W_FIRST + W_LAST - 2 * W_MID)) / 6)


def speech_dur(rate, base_speech):
    return base_speech / (1.0 - RATE_K * (1.0 - rate))


def rate_for_speech(target_speech, base_speech):
    ratio = base_speech / max(1e-6, target_speech)
    r = 1.0 - (1.0 - ratio) / RATE_K
    return max(0.55, min(1.95, r))


def nwords(s):
    return len(re.findall(r"[A-Za-z0-9']+", s))


# ---------------------------------------------------------------- 文本切分

def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_clauses(para):
    sents = re.findall(r"[^.!?]+[.!?]*", para)
    out = []
    for sid, s in enumerate(sents):
        s = s.strip()
        if not s:
            continue
        parts = re.split(r"([,;:—–]|(?<=\w)-(?=\w))", s)
        buf, chunks = "", []
        for p in parts:
            if p in (",", ";", ":", "—", "–", "-"):
                if buf.strip():
                    chunks.append((buf.strip(), p))
                buf = ""
            else:
                buf += p
        buf = buf.strip()
        if buf:
            m = re.search(r"([.!?])$", buf)
            if m and buf[:m.start()].strip():
                chunks.append((buf[:m.start()].strip(), m.group(1)))
            elif buf:
                chunks.append((buf, ""))
        for k, (body, punct) in enumerate(chunks):
            out.append(dict(body=body, punct=punct, sent=sid,
                            cin=k, ncin=len(chunks),
                            sent_end=(k == len(chunks) - 1)))
    return out


# ---------------------------------------------------------------- 文本分析

def analyze(text):
    paras = split_paragraphs(text)
    feats = []
    for pi, para in enumerate(paras):
        cls = split_clauses(para)
        if not cls:
            continue
        n_sent = max(c["sent"] for c in cls) + 1

        # 枚举检测：连续 >=2 个逗号子句
        list_flags = [False] * len(cls)
        i = 0
        while i < len(cls):
            if cls[i]["punct"] == "," and not cls[i]["sent_end"]:
                j = i
                while j < len(cls) and cls[j]["punct"] == "," and not cls[j]["sent_end"]:
                    j += 1
                if j - i >= 2:
                    for k in range(i, j):
                        list_flags[k] = True
                i = j
            else:
                i += 1

        for ci, c in enumerate(cls):
            body = c["body"]
            nw = nwords(body)
            toks = body.split()
            first_word = re.sub(r"[^A-Za-z']", "", toks[0]).lower() if toks else ""
            sent_text = " ".join(x["body"] for x in cls if x["sent"] == c["sent"])

            if c["punct"] == "?":
                stype = "question"
            elif c["punct"] == "!":
                stype = "exclaim"
            elif body[:1] in ('"', "“", "'") or body[-1:] in ('"', "”"):
                stype = "quote"
            else:
                stype = "statement"

            emph = []
            for w in toks:
                bare = re.sub(r"[^A-Za-z0-9']", "", w)
                if not bare:
                    continue
                if len(bare) >= 3 and bare.isupper() and bare.lower() not in STOPWORDS:
                    emph.append(bare)
                elif "*" in w and len(bare) >= 3:
                    emph.append(bare)
                elif re.search(r"\d", bare):
                    emph.append(bare)

            feats.append(dict(
                para=pi, n_para=len(paras),
                para_start=(c["sent"] == 0 and c["cin"] == 0),
                para_end=(c["sent"] == n_sent - 1 and c["sent_end"]),
                sent=c["sent"], cin=c["cin"], ncin=c["ncin"], sent_end=c["sent_end"],
                body=body, punct=c["punct"], nw=nw,
                first_word=first_word, stype=stype,
                in_list=list_flags[ci],
                list_last=(list_flags[ci] and (ci + 1 >= len(cls) or not list_flags[ci + 1])),
                long_clause=(nw >= 12),
                connective=(first_word in CONNECTIVES),
                emph=emph,
                sent_words=nwords(sent_text),
            ))
    return feats


# ---------------------------------------------------------------- 决策

def decide(f, base_rate, pause_scale):
    reasons = []
    r = base_rate

    nw = f["nw"]
    if nw <= 3:
        r *= 0.92; reasons.append("短句(%d词)放慢" % nw)
    elif nw <= 5:
        r *= 0.97; reasons.append("%d词略慢" % nw)
    elif nw >= 12:
        r *= 1.06; reasons.append("长句(%d词)略快" % nw)

    if f["para_start"]:
        r *= 0.94; reasons.append("段首铺垫放慢")
    if f["para_end"]:
        r *= 0.88; reasons.append("段末收尾放慢")

    if f["stype"] == "exclaim":
        r *= 1.08; reasons.append("感叹句加快")
    elif f["stype"] == "quote":
        r *= 0.96; reasons.append("引语放慢")

    if f["connective"]:
        r *= 0.97; reasons.append("连接词起句放慢")

    r = round(max(0.55, min(1.95, r)), 2)
    if r == 1.0:
        r = 1.01

    gap = PAUSE_TARGET.get(f["punct"], 0.0) if f["punct"] else 0.0
    if f["punct"]:
        reasons.append("标点 %s → %.2fs" % (f["punct"], gap))
    if f["in_list"]:
        if f["list_last"]:
            gap += 0.25; reasons.append("枚举末项蓄势 +0.25")
        else:
            gap -= 0.12; reasons.append("枚举项等距 -0.12")
    if f["connective"]:
        gap += 0.12; reasons.append("连接词换气 +0.12")
    if f["long_clause"]:
        gap += 0.20; reasons.append("长句换气 +0.20")
    if f["para_end"]:
        gap += 0.60; reasons.append("段末长停 +0.60")
    if f["punct"]:
        gap = max(0.0, gap * pause_scale)

    pitch = None
    if f["stype"] == "question" and f["sent_end"]:
        pitch = 3; reasons.append("问句句尾上扬 +3 半音")
    elif f["stype"] == "exclaim" and f["sent_end"]:
        pitch = 2; reasons.append("感叹句 +2 半音")

    return r, gap, pitch, reasons


def pause_tags(extra_seconds):
    extra_seconds = max(0.0, extra_seconds)
    tags, used = [], 0.0
    for _ in range(PAUSE_MAX_STACK):
        best = 0
        for lv, step in sorted(PAUSE_STEP.items(), reverse=True):
            if used + step <= extra_seconds + 1e-9:
                best = lv
                break
        if not best:
            break
        tags.append('<pause act="ins" level="%d"/>' % best)
        used += PAUSE_STEP[best]
    return tags, used


# ---------------------------------------------------------------- 编译

def merge_adjacent_rate(xml):
    """合并相邻同 factor 的 rate span（中间只有空白时）。
    官方语义是「局部操作」，相邻同值可视为一个 span；减少标签数可降低丢词风险。
    """
    pat = re.compile(r"<rate, factor=([0-9.]+)>(.*?)</rate>", re.S)
    items, pos = [], 0
    for m in pat.finditer(xml):
        between = xml[pos:m.start()]
        f, body = m.group(1), m.group(2)
        if items and items[-1][0] == f and between.strip() == "":
            items[-1][1] = items[-1][1] + " " + body
        else:
            items.append([f, body])
        pos = m.end()
    if not items:
        return xml
    merged = " ".join("<rate, factor=%s>%s</rate>" % (f, b) for f, b in items)
    tail = xml[pos:].strip()
    return merged + (" " + tail if tail else "")


def compile_text(text, mode="mc", target_wpm=145.0, base_wpm=None,
                 pause_scale=1.30, stretch_last_word=True, emit_pause_tags=False):
    feats = analyze(text)
    if not feats:
        return "", [], [], []

    total_words = sum(f["nw"] for f in feats)
    if base_wpm is None:
        base_wpm = BASE_WORDS / BASE_SPEECH * 60

    target_speech = total_words / target_wpm * 60
    base_speech = total_words / base_wpm * 60
    base_rate = round(rate_for_speech(target_speech, base_speech), 2)
    if base_rate == 1.0:
        base_rate = 1.01

    pieces, timeline, explain = [], [], []
    clock = 0.0
    for i, f in enumerate(feats):
        if mode == "bare":
            rate, pitch, reasons = 1.0, None, ["bare 模式：只插停顿"]
            gap_t = (PAUSE_TARGET.get(f["punct"], 0.0) if f["punct"] else 0.0) * pause_scale
        elif mode == "flat":
            rate, pitch, reasons = base_rate, None, ["flat：全段统一 rate %.2f" % base_rate]
            gap_t = (PAUSE_TARGET.get(f["punct"], 0.0) if f["punct"] else 0.0) * pause_scale
        else:
            rate, gap_t, pitch, reasons = decide(f, base_rate, pause_scale)

        # ★ 标点必须回到文本里：instruction 是模型主输入，缺句读会影响韵律判断
        P = f["punct"] or ""
        body, words = f["body"] + P, f["body"].split()

        # ---- 一个 span 一个标签，严格按源序并列 ----
        if pitch is not None:
            pieces.append('<pitch semitones="%d">%s</pitch>' % (pitch, body))
        elif mode == "mc" and stretch_last_word and f["sent_end"] and len(words) >= 3:
            pieces.append('<rate factor="%s">%s</rate>' % (rate, " ".join(words[:-1])))
            pieces.append('<rate factor="0.55">%s</rate>' % (words[-1] + P))
        elif mode == "mc" and f["emph"]:
            pat = "|".join(re.escape(w) for w in f["emph"])
            for s in re.split(r"(\b(?:%s)\b)" % pat, body):
                if not s.strip():
                    continue
                if re.sub(r"[^A-Za-z0-9']", "", s).lower() in [w.lower() for w in f["emph"]]:
                    pieces.append('<rate factor="%.2f">%s</rate>' % (max(0.55, rate * 0.94), s))
                else:
                    pieces.append('<rate factor="%s">%s</rate>' % (rate, s))
        else:
            pieces.append('<rate factor="%s">%s</rate>' % (rate, body))

        est = speech_dur(rate, f["nw"] / base_wpm * 60)
        clock += est + (BASE_GAP if f["punct"] else 0.0)
        row = dict(idx=i, text=body, punct=f["punct"], nw=f["nw"], rate=rate,
                   stype=f["stype"], est_speech=round(est, 2), clock=round(clock, 2),
                   reasons=reasons, gap_tag=0.0, gap_est=0.0,
                   gap_target=round(gap_t, 2) if f["punct"] else 0.0)
        timeline.append(row)

        if f["punct"]:
            extra = max(0.0, gap_t - BASE_GAP)
            # ★ 默认不生成 <pause>：实测 rate 与 pause 混用会跳词，停顿一律走后期
            if emit_pause_tags:
                tags, used = pause_tags(extra)
                if tags:
                    pieces.append("".join(tags))
                    clock += used
            else:
                used = 0.0
            row["gap_tag"] = round(used, 2)
            row["gap_est"] = round(BASE_GAP + used, 2)
            row["residual"] = round(max(0.0, extra - used), 2)
            if row["residual"] > 0.05:
                row["reasons"].append("⚠ 需 %.2fs，标签只给 %.2fs → 后期补 %.2fs" % (
                    extra, used, row["residual"]))

        explain.append(row)

    # ---- 停顿计划（给后期 insert_pauses.py 用；标签补不到的部分走这里） ----
    pause_plan = []
    for r in timeline:
        if r["gap_target"] > 0:
            pause_plan.append(dict(idx=r["idx"], after_text=r["text"], punct=r["punct"],
                                   target_s=r["gap_target"],
                                   tag_s=r["gap_tag"],
                                   residual_s=round(max(0.0, r["gap_target"] - BASE_GAP), 2)))

    tagged = " ".join(pieces)
    tagged = re.sub(r"\s+([,.;:!?])", r"\1", tagged)
    tagged = re.sub(r"\s{2,}", " ", tagged)
    # ★ 官方要求：<rate, factor=0.83> / <pitch, semitones=3> / <pause ... level="2"/>
    tagged = MK.to_model_format(tagged)
    # 相邻同速 span 合并，减少标签数量（官方语义允许，且能降低丢词风险）
    tagged = merge_adjacent_rate(tagged)
    return tagged, timeline, explain, pause_plan


# ---------------------------------------------------------------- 校验

_TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w-]*)([^>]*?)(/?)>")


def validate(tagged):
    stack, errs = [], []
    for m in _TAG_RE.finditer(tagged):
        closing, name, attrs, selfclose = m.groups()
        if selfclose:
            continue
        if closing:
            if not stack:
                errs.append("多余的闭合标签 </%s>" % name)
            elif stack[-1] != name:
                errs.append("交叉/错配：期望 </%s> 得到 </%s>" % (stack[-1], name))
                if name in stack:
                    while stack and stack[-1] != name:
                        stack.pop()
                    if stack:
                        stack.pop()
            else:
                stack.pop()
        else:
            if stack:
                errs.append("嵌套违规：<%s> 出现在 <%s> 内部" % (name, stack[-1]))
            stack.append(name)
    if stack:
        errs.append("未闭合：%s" % ", ".join(stack))
    return errs


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--out", dest="out")
    ap.add_argument("--json", dest="js")
    ap.add_argument("--mode", default="mc", choices=["bare", "flat", "mc"])
    ap.add_argument("--emit-pause-tags", action="store_true",
                    help="在文本里生成 <pause>（默认关闭：实测与 rate 混用会跳词，停顿走后期）")
    ap.add_argument("--target-wpm", type=float, default=145.0)
    ap.add_argument("--base-wpm", type=float, default=None)
    ap.add_argument("--pause-scale", type=float, default=1.30)
    ap.add_argument("--no-stretch", action="store_true")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--safe", action="store_true",
                    help="只输出整段一个 <rate>（实测唯一不丢词的组合），停顿走 pause_plan")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    text = sys.stdin.read() if a.stdin else open(a.inp, encoding="utf-8").read()
    tagged, tl, ex, plan = compile_text(text, mode=a.mode, target_wpm=a.target_wpm,
                                  base_wpm=a.base_wpm, pause_scale=a.pause_scale,
                                  stretch_last_word=not a.no_stretch,
                                  emit_pause_tags=a.emit_pause_tags)
    if a.safe:
        # 实测：多个 rate span / 多个 pause / 二者混用 都会丢词；整段一个 rate 最稳
        tw = sum(r["nw"] for r in tl)
        bw = a.base_wpm or BASE_WORDS / BASE_SPEECH * 60
        r = round(rate_for_speech(tw / a.target_wpm * 60, tw / bw * 60), 2)
        if r == 1.0:
            r = 1.01
        tagged = MK.rate(re.sub(r"\s+", " ", text).strip(), r)

    _ok, errs, _warns = MK.validate(tagged)

    if not a.quiet:
        tw = sum(r["nw"] for r in tl)
        print("=" * 82)
        print("模式 %s | %d 子句 / %d 词 | 目标 %.0f wpm | 停顿 x%.2f" % (
            a.mode, len(tl), tw, a.target_wpm, a.pause_scale))
        print("真人对照 %.2fs（语音 %.2f + 静音 %.2f）" % (REAL_TOTAL, REAL_SPEECH, REAL_TOTAL - REAL_SPEECH))
        print("-" * 82)
        print("%-3s %-38s %3s %5s %6s %6s %-9s" % ("#", "子句", "词", "rate", "语音", "累计", "类型"))
        for r in tl:
            print("%-3d %-38s %3d %5.2f %6.2f %6.2f %-9s" % (
                r["idx"] + 1, r["text"][:38], r["nw"], r["rate"],
                r["est_speech"], r["clock"], r["stype"]))
        print("-" * 82)
        print("估算总长 %.2fs（真人 %.2fs，差 %+.2fs）" % (
            tl[-1]["clock"], REAL_TOTAL, tl[-1]["clock"] - REAL_TOTAL))
        print("校验: %s" % ("✅ 无嵌套、标签平衡" if not errs else "❌ " + " | ".join(errs)))
        if a.explain:
            print("-" * 82)
            print("决策依据（按文字内容）")
            for r in ex:
                print("  #%d %s" % (r["idx"] + 1, r["text"][:34]))
                print("      " + " · ".join(r["reasons"]))
        print("=" * 82)
        print()
        print(tagged)
        print()

    if a.out:
        open(a.out, "w", encoding="utf-8").write(tagged + "\n")
        print("→ %s" % a.out, file=sys.stderr)
    if a.js:
        json.dump(dict(mode=a.mode, safe=a.safe, target_wpm=a.target_wpm, plan=tl,
                       tagged=tagged, pause_plan=plan, errors=errs),
                  open(a.js, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
