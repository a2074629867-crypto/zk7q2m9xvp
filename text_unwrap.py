"""把 PDF 转 EPUB 时被硬换行劈开的长行接回去

PDF→EPUB 转换把每一行排版行都当成一个 <p>，所以一句话经常被劈成 2–3 段：
    "And he shrank from the expression"
    "in the boy's eyes, from his knowingness."
直接按行切句会切出大量 3–7 词的碎片。这里先做「续行合并」再交给切句器。

续行判据（三条任一成立就并到下一行）：
1. 行尾没有句末标点 . ! ?  （逗号、分号、破折号收尾都是续行）
2. 行尾是字母（说明句子还没完，PDF 只是换行）
3. 引号未配平（一句话的引号跨行了）
"""
import re


def unquote_balance(s: str) -> int:
    """返回未配平的引号数（正数=左引号多）。"""
    return (s.count("‘") + s.count("“") + s.count("'") - s.count("’") * 0 - s.count("”")) - s.count("’")


def _quotes_open(s: str) -> bool:
    """单引号/双引号是否有未闭合（PDF 里 ’ 既是右引号也是撇号，用 ‘ 计数）。"""
    left_single = s.count("‘")
    right_single = s.count("’")
    left_double = s.count("“")
    right_double = s.count("”")
    # 撇号 (don’t / boy’s) 会让 right_single 虚高，扣掉「字母+’+字母」
    apostrophe = len(re.findall(r"(?<=[A-Za-z])’(?=[A-Za-z])", s))
    right_single -= apostrophe
    return (left_single - right_single) > 0 or (left_double - right_double) > 0


END_PUNCT = ".!?…"
CLOSERS = "’'\"”’)]"


def needs_continue(line: str, nxt: str) -> bool:
    s = line.rstrip()
    if not s:
        return False
    if _quotes_open(s):
        return True
    core = s
    # 去掉行尾的引号/括号后再看标点
    while core and core[-1] in CLOSERS:
        core = core[:-1].rstrip()
    if not core:
        return False
    last = core[-1]
    if last in END_PUNCT:
        return False
    # 以字母、逗号、分号、冒号、破折号、连字符收尾 → 续行
    return True


def unwrap(lines, max_join=6):
    """把连续的排版行合并回段落。"""
    out = []
    buf = ""
    joins = 0
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if not buf:
            buf = t
            joins = 0
            continue
        if needs_continue(buf, t) and joins < max_join:
            # 断词连字符：forward-  /  tion → 直接黏
            if buf.endswith("-") and t[:1].islower():
                buf = buf[:-1] + t
            else:
                buf = buf + " " + t
            joins += 1
            continue
        out.append(buf)
        buf = t
        joins = 0
    if buf:
        out.append(buf)
    return out
