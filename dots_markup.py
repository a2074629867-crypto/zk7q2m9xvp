# -*- coding: utf-8 -*-
"""
dots.tts 标记规则（官方规范 + 本项目实测约束）
==============================================
单一事实来源。所有生成脚本必须经由本模块构造标签，不要手写 XML 字符串。

## 一、两种格式，别混

标准 XML（doteBench 数据契约 / 人写）:
    <rate factor="1.20">faster</rate>
    <pitch semitones="4">higher</pitch>
    <pause act="ins"/>

模型格式（dots.tts.edit 实际吃的 token 序列）:
    <rate, factor=1.20>faster</rate>
    <pitch, semitones=4>higher</pitch>
    <pause act="ins" level="2"/>

差异三条（来自 doteBench/src/dotebench/candidates/dots_tts_edit/compile.py）:
    1. 属性分隔符是「逗号」不是空格
    2. 数值不加引号
    3. <pause> 必须补 level（官方固定 2）

compile.py 原注释：
    "Read attribute strings directly: float conversion would lose lexical
     precision (for example 1.20), changing the model's token sequence."
⇒ 数值的词法形式会改变 token 序列，1.20 ≠ 1.2。构造时按目标精度直接格式化，
  不要先转 float 再拼。

<sub>/<del>/<ins>/<emo> 不做转换，保持标准写法。

## 二、官方支持的粒度

doteBench prosody 集 360 例的 span_granularity 分布：
    single_word 108 (30%) / short_phrase 108 (30%) / clause 120 (33%) / sentence 24 (7%)
⇒ 词级 rate/pitch 是设计内的能力，不是滥用。

## 三、情绪

type 八种（612 个情绪样例的实测取值）：
    disgusted 110 / angry 109 / melancholic 109 / happy 109
    sad 109 / surprised 109 / afraid 109 / calm 52
level 1–3（data.md: "Emotion levels are 1–3"），官方样例全部用 2。

## 四、停顿

<pause act="ins"/>  插入停顿
<pause act="red"/>  减少停顿
模型格式必须带 level，官方适配器固定写 level="2"。

## 五、三条铁律（官方 data.md）

1. Operations cannot nest or cross —— 不能嵌套、不能交叉
2. 所有操作都是局部的
3. xvector 自动开关：
     只有 emo / bg / enhance        → 关闭（音色来自 voice_ref）
     含 sub/ins/del/pitch/rate/pause → 开启（音色来自 source_audio）
   可用 --use-xvector on|off 强制覆盖。
   ★ 本项目音色来自 source_audio，若要只用 emo，必须显式 --use-xvector on。

## 六、多操作：用 sequential，不要一次塞

官方两种编译方式：
   one_take   整条指令一次调用
   sequential 先文本标签（sub/ins/del），再声学标签（emo/pitch/rate/pause），
              每个操作单独一步，上一步输出作为下一步输入
planner.py: "Execute text tags first, then acoustic tags, preserving each XML order."

## 七、本项目实测约束（不是官方规定）

- 多个 <rate> span 在同一块内会丢子句（9 span 丢 1、11 span 丢 2）
  → 但当时用的是错误格式，待用模型格式重测
- 连续叠 ≥2 个 <pause> 会整段跳词（38 词只剩 10 词）
- <rate> 与 <pause> 混用会跳词
- 单块约 130 词（max_tokens 上限，≈0.0432s/patch）
"""
from __future__ import annotations

import re

# ------------------------------------------------------------------ 常量
# 官方 parser（doteBench/src/dotebench/instructions/parser.py:18 EMOTIONS）允许 9 种，
# 其中 neutral 在 624 个 emotion 样例里从未出现，但 parser 不报错 ⇒ 合法可用。
EMO_TYPES = (
    "angry", "afraid", "sad", "happy", "surprised",
    "disgusted", "melancholic", "calm", "neutral",
)
# 官方 624 例 emotion 样例 level 全部是 2（无一例 1 或 3）；实测 L1/L2/L3 的 F0 完全一致
# ⇒ level 只接受 2，写别的值等于不写。
EMO_LEVEL_OFFICIAL = 2
EMO_LEVELS = (1, 2, 3)          # parser 接受，但模型无梯度，仅保留兼容
PAUSE_ACTS = ("ins", "red")
GRANULARITY = ("single_word", "short_phrase", "clause", "sentence")
# 官方 emo span 词数：phrase 中位 2–3、最长 12；实测 1 词会插假声、42 词整段毁音色。
EMO_SPAN_WORDS_OFFICIAL_MAX = 12
EMO_SPAN_WORDS_SAFE = 11        # 本项目实测声纹 0.8858 仍合格的上限

# 官方组合集里 emo 与 rate 共存时的 rate 取值：只有 0.8(17次) 和 1.25(16次) 两个档。
# ⇒ 官方把 rate 当「两档表演」，不做精细调速；且 emo 与 rate 各包不同片段，从不重叠。
RATE_COMBO_VALUES = (0.80, 1.25)
# 官方 1,152 例的分布：emotion 集 612 例含 rate 0 次，prosody 集 360 例含 emo 0 次
# ⇒ 官方严格分离「情绪实验」与「韵律实验」，只在 compositional 里混用（含 emo+rate 33 例）。

# xvector 自动关闭集合（compile.py / edit_instruction.py 一致）
AUTO_DISABLE_XVECTOR = frozenset({"emo", "bg", "enhance"})

# 本项目停顿目标（秒），来自母带 26.92min / 641 间隙实测
PAUSE_SECONDS = {
    ".": 1.76, "?": 1.76, "!": 1.76,
    ",": 1.17,
    ";": 1.28, ":": 1.28,
    "para": 2.50,
    "breath": 0.20,
    "micro": 0.10,
}

TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z_][\w-]*)")
CONTAINER = frozenset({"del", "ins", "sub", "emo", "pitch", "rate", "enhance", "bg"})
EMPTY = frozenset({"pause", "spk_transfer"})


class MarkupError(ValueError):
    pass


# ------------------------------------------------------------------ 数值
def _num(v, nd=None):
    """按目标精度直接格式化，避免 float 词法漂移。"""
    if nd is not None:
        return ("%." + str(nd) + "f") % float(v)
    s = ("%g" % float(v))
    return s


# ------------------------------------------------------------------ 构造（模型格式）
def rate(text, factor, nd=2):
    """<rate, factor=0.83>text</rate>"""
    if float(factor) <= 0:
        raise MarkupError("rate factor 必须为正数")
    return "<rate, factor=%s>%s</rate>" % (_num(factor, nd), text)


def pitch(text, semitones):
    """<pitch, semitones=3>text</pitch>"""
    v = float(semitones)
    s = ("%d" % v) if abs(v - int(v)) < 1e-9 else _num(v, 2)
    return "<pitch, semitones=%s>%s</pitch>" % (s, text)


def pause(act="ins", level=2):
    """<pause act="ins" level="2"/>"""
    if act not in PAUSE_ACTS:
        raise MarkupError("pause act 只能是 ins / red")
    if int(level) not in EMO_LEVELS:
        raise MarkupError("pause level 只能是 1-3")
    return '<pause act="%s" level="%d"/>' % (act, int(level))


def emo(text, type_, level=2):
    """<emo type="calm" level="2">text</emo>"""
    if type_ not in EMO_TYPES:
        raise MarkupError("emo type 必须是 %s 之一" % "/".join(EMO_TYPES))
    if int(level) not in EMO_LEVELS:
        raise MarkupError("emo level 只能是 1-3")
    return '<emo type="%s" level="%d">%s</emo>' % (type_, int(level), text)


def emo_desc(text, desc, level=2):
    """自由描述形式 <emo desc="..." level="2">。官方 data.md 未定义 desc，
    实际效果取决于训练数据，慎用；优先用 EMO_TYPES 枚举。"""
    return '<emo desc="%s" level="%d">%s</emo>' % (desc, int(level), text)


def sub(old, new):
    """<sub targ="new">old</sub>"""
    return '<sub targ="%s">%s</sub>' % (new, old)


def ins(text):
    return "<ins>%s</ins>" % text


def dele(text):
    return "<del>%s</del>" % text


# ------------------------------------------------------------------ 标准 XML → 模型格式
def to_model_format(xml):
    """
    把标准 XML 转成模型格式。规则与 compile.py 完全一致：
      <rate factor="x">      → <rate, factor=x>
      <pitch semitones="n">  → <pitch, semitones=n>
      <pause ...>            → <pause ... level="2">
    若 pause 已带 level，则替换为 2，不重复追加（compile.py 原版会重复，这是它的 bug）。
    """
    def _prosody(m):
        tag = m.group(1)
        attr = "semitones" if tag == "pitch" else "factor"
        mm = re.search(r'\b%s\s*=\s*["\']?([^"\'>\s]+)' % attr, m.group(0))
        if not mm:
            raise MarkupError("%s 缺少 %s 属性: %s" % (tag, attr, m.group(0)))
        return "<%s, %s=%s>" % (tag, attr, mm.group(1))

    out = re.sub(r"<(rate|pitch)\b[^>]*>", _prosody, xml)

    def _pause(m):
        body = m.group(0)
        close = "/>" if body.endswith("/>") else ">"
        core = body[:-len(close)].rstrip()
        # 已有 level 就保留（本项目用 level 控制补多少秒），没有才补官方默认 2
        if re.search(r"\blevel\s*=", core):
            return core + close
        return core + ' level="2"' + close

    return re.sub(r"<pause\b[^>]*>", _pause, out)


# ------------------------------------------------------------------ 校验
def validate(xml):
    """
    检查：标签配对、嵌套/交叉违规、未知标签。
    返回 (ok, errors, warnings)
    """
    errs, warns = [], []
    stack = []
    for m in TAG_RE.finditer(xml):
        closing, name = m.group(1) == "/", m.group(2)
        if name not in CONTAINER and name not in EMPTY:
            warns.append("未知标签 <%s>" % name)
            continue
        if name in EMPTY:
            continue
        if not closing:
            stack.append(name)
        else:
            if not stack:
                errs.append("多余闭合 </%s>" % name)
            elif stack[-1] != name:
                errs.append("交叉/错配：期望 </%s>，实际 </%s>" % (stack[-1], name))
                stack.pop()
            else:
                stack.pop()
    if stack:
        errs.append("未闭合：%s" % ", ".join("<%s>" % s for s in stack))

    # 本项目实测风险提示（非官方规定）
    tags = {m.group(2) for m in TAG_RE.finditer(xml) if m.group(1) != "/"}
    if "rate" in tags and "pause" in tags:
        warns.append("rate 与 pause 混用：旧格式实测整段跳词，建议停顿改走后期")
    n_rate = sum(1 for m in TAG_RE.finditer(xml) if m.group(2) == "rate" and m.group(1) != "/")
    if n_rate > 10:
        warns.append("rate span 数 %d > 10：实测 9 span 安全、29 span 丢整段，建议合并到 10 以内" % n_rate)

    # emo 相关（官方规范 + 本项目实测）
    emo_spans = []
    for m in re.finditer(r"<emo\b([^>]*)>(.*?)</emo>", xml, re.S):
        attrs, body = m.group(1), m.group(2)
        emo_spans.append(body)
        w = len(body.split())
        if w > EMO_SPAN_WORDS_OFFICIAL_MAX:
            warns.append("emo span %d 词 > 官方上限 %d：官方 624 例最长 12 词，再长音色开始下滑；"
                         "42 词整段时声纹 0.95→0.38（整段切到 8s voice_ref）"
                         % (w, EMO_SPAN_WORDS_OFFICIAL_MAX))
        elif w <= 3:
            warns.append("emo span 仅 %d 词：官方 624 例全部是完整从句（英文中位 8 词、最短 4 词），"
                         "单词级实测会在该词后插入 0.1s 高频假声，听感像吸气而非情绪" % w)
        tm = re.search(r'type\s*=\s*"([^"]*)"', attrs)
        if not tm:
            errs.append("emo 缺 type：官方 parser 要求 type 与 level 同时存在")
        elif tm.group(1) not in EMO_TYPES:
            errs.append("emo type=%r 不在官方 9 种枚举内（%s）；官方 parser 直接 raise ValueError"
                        % (tm.group(1), "/".join(EMO_TYPES)))
        if "level=" not in attrs:
            errs.append('emo 缺 level：官方 parser 要求 type 与 level 同时存在（ATTRS["emo"]={"type","level"}）')
        elif 'level="2"' not in attrs:
            warns.append("emo level 非 2：官方 624 例全部用 2，实测 L1/L2/L3 无梯度 ⇒ 建议固定 2")

    # emo + rate 共存（官方组合集范式 vs 我们的实测）
    if emo_spans and "rate" in tags:
        warns.append("emo 与 rate 同块：官方组合集要求二者分片段、不重叠（rate 只取 0.8/1.25）；"
                     "本项目实测 rate 会被 emo 抑制（0.88 → 兑现 84% → 0%），建议二选一或走 sequential")
        # 兼容两种写法：<rate, factor=0.88>（模型格式）与 <rate factor="0.88">（标准 XML）
        for m in re.finditer(r'<rate[,\s]+factor\s*=\s*"?([\d.]+)"?', xml):
            try:
                f = float(m.group(1))
            except ValueError:
                continue
            if not any(abs(f - v) < 0.005 for v in RATE_COMBO_VALUES):
                warns.append("组合场景 rate=%.2f 不在官方取值（0.80 / 1.25）内" % f)
                break

    # 嵌套违规（官方 Operations cannot nest or cross）
    depth = 0
    for m in TAG_RE.finditer(xml):
        closing, name = m.group(1) == "/", m.group(2)
        if name in EMPTY:
            continue
        if not closing:
            depth += 1
            if depth > 1:
                errs.append("操作嵌套：<%s> 位于另一操作内部" % name)
                break
        else:
            depth = max(0, depth - 1)
    return (not errs), errs, warns


def needs_xvector(xml):
    """按官方规则判断是否需要开 xvector。"""
    tags = {m.group(2) for m in TAG_RE.finditer(xml) if m.group(1) != "/"}
    tags -= EMPTY
    if not tags:
        return False
    return not tags.issubset(AUTO_DISABLE_XVECTOR)


def describe(xml):
    """给一段标记做人话解释，便于日志核对。"""
    tags = [m.group(2) for m in TAG_RE.finditer(xml) if m.group(1) != "/"]
    from collections import Counter
    c = Counter(tags)
    return " · ".join("%s×%d" % (k, v) for k, v in c.items()) or "无标签"


if __name__ == "__main__":
    demo = ('<rate factor="0.83">Hello there</rate>'
            '<pause act="ins"/>'
            '<emo type="calm" level="2">goodnight</emo>')
    print("标准 XML :", demo)
    print("模型格式 :", to_model_format(demo))
    print("校验     :", validate(to_model_format(demo)))
    print("需xvector:", needs_xvector(demo))
    print("停顿表   :", PAUSE_SECONDS)
