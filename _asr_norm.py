# -*- coding: utf-8 -*-
"""_asr_norm.py —— ASR 覆盖率的口径归一化（修假阳性）。

2026-10-30 实测暴露的问题：13 条里 4 条被判「漏词」，逐条看全是**口径错，不是真吞字**：

    mrs          ASR 念 missus / misses      → 缩写，词形永远对不上
    thirty + seven   ASR 输出 thirtyseven    → 连字符被合成一个词

如果不修，回环会把这几条反复送去重生成 —— 白烧算力，而且永远过不了。

匹配规则（由严到宽，命中即算对上）：
  1. 精确相等
  2. 缩写白名单等价（mrs ↔ missus/misses …）
  3. 数字连字符：两个 ref 词拼起来等于某个 hyp 词（thirty + seven → thirtyseven）
  4. 前缀容忍：ref 词（≥4 字母）是某个 hyp 词的前缀，或反之（长度差 ≤6）

第 4 条有误配风险（four 会匹配 fourteen），所以把每一次「非精确匹配」都记进
tolerant 列表，由调用方打印出来人工扫一眼。宁可多记，不要静默吞掉。

用法：
    from _asr_norm import cover
    cov, miss, tol = cover(ref_words, hyp_words)
"""
import difflib

# 缩写 → 可能的读法。值里含自身便于直接查表。
ABBR = {
    "mrs": {"mrs", "missus", "misses", "missis", "mistress"},
    "mr": {"mr", "mister"},
    "dr": {"dr", "doctor"},
    "st": {"st", "saint", "street"},
    "jr": {"jr", "junior"},
    "sr": {"sr", "senior"},
    "vs": {"vs", "versus"},
    "etc": {"etc", "etcetera"},
    "no": {"no", "number"},
    "mt": {"mt", "mount"},
    "ft": {"ft", "fort"},
    "ave": {"ave", "avenue"},
    "rd": {"rd", "road"},
}

NUM_ONES = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}
NUM_TEENS = {"ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
             "sixteen", "seventeen", "eighteen", "nineteen"}
NUM_TENS = {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}

MIN_PREFIX = 4
MAX_LEN_DIFF = 6


def _is_num_pair(a, b):
    """thirty + seven / twenty + one 这种「十位 + 个位」组合。"""
    return (a in NUM_TENS and b in NUM_ONES) or (a in NUM_ONES and b in NUM_TENS)


def cover(ref, hyp, max_shift=2):
    """返回 (cov, miss, tolerant)。

    cov      匹配词数 / ref 词数
    miss     真正没对上的 ref 词
    tolerant [(ref词, 匹配到的 hyp 词, 规则)] —— 非精确匹配，供人工核查
    """
    n = len(ref)
    if not n:
        return 0.0, [], []

    hyp_left = list(hyp)                 # 可被消费的 hyp 词
    used = [False] * len(hyp_left)
    tol = []
    miss = []
    skip = set()                         # 被连字符规则一次覆盖掉的后一个 ref 词
    ok = 0

    for i, w in enumerate(ref):
        if i in skip:
            continue
        hit = None
        # 1 精确
        for j, h in enumerate(hyp_left):
            if not used[j] and h == w:
                hit = (j, "exact")
                break
        # 2 缩写
        if hit is None and w in ABBR:
            for j, h in enumerate(hyp_left):
                if not used[j] and h in ABBR[w]:
                    hit = (j, "abbr")
                    break
        # 3 数字连字符：ref[i] + ref[i+1] 拼起来 == 某 hyp 词（一次覆盖两个 ref 词）
        if hit is None and i + 1 < len(ref) and _is_num_pair(w, ref[i + 1]):
            joint = w + ref[i + 1]
            for j, h in enumerate(hyp_left):
                if not used[j] and h == joint:
                    used[j] = True
                    skip.add(i + 1)
                    ok += 2
                    tol.append((w + "+" + ref[i + 1], h, "hyphen"))
                    hit = (-1, "hyphen")
                    break
            if hit is not None:
                continue
        # 4 前缀容忍（方向敏感，防止把真漏词当成连字符合成）
        #   hyp 比 ref 长 → 可能是连字符合成（thirty → thirtyseven），允许 +4
        #   hyp 比 ref 短 → 只容忍词尾差 2 以内，再多就是真漏了
        if hit is None and len(w) >= MIN_PREFIX:
            for j, h in enumerate(hyp_left):
                if used[j]:
                    continue
                d = len(h) - len(w)
                if h.startswith(w) and 0 <= d <= 4:
                    hit = (j, "prefix+")
                    break
                if 0 <= -d <= 2 and w.startswith(h):
                    hit = (j, "prefix-")
                    break

        if hit is None:
            miss.append(w)
            continue
        j, rule = hit
        used[j] = True
        ok += 1
        if rule != "exact":
            tol.append((w, hyp_left[j], rule))

    cov = ok / n
    return cov, miss, tol


def fix_text(text):
    """把粘连的数字词补回空格：`thirtyseven` -> `thirty seven`。

    只动「十位+个位」这一种确定形态，不碰其他词，避免误伤。
    门禁在 predict 之前必须先过这一层，否则 ref 1 词 / ASR 2 词必然对不上。
    """
    import re

    def rep(m):
        t = m.group(0)
        sp = _split_num(t.lower())
        if not sp:
            return t
        # 保持原大小写形态：首字母大写则两段都按原样输出
        return sp[0] + " " + sp[1]

    return re.sub(r"[A-Za-z]+", rep, text)


def words(text):
    """与 ASR/ref 一致的词提取（只留字母，转小写）。

    额外处理「粘连数字词」：EPUB 预处理会把 `thirty-seven` 的连字符删掉且不补空格，
    于是参考文本里出现 `thirtyseven`（N0187 实测），而 ASR 正常输出 `thirty-seven`
    → 词序列一边 1 个词、一边 2 个词，被判成漏词。这里把 十位+个位 的粘连拆开。
    """
    import re
    out = []
    for t in re.findall(r"[A-Za-z]+", text):
        t = t.lower()
        sp = _split_num(t)
        out.extend(sp if sp else [t])
    return out


def _split_num(t):
    """thirtyseven -> ['thirty','seven']；非数字词返回 None。"""
    for tens in NUM_TENS:
        if t.startswith(tens):
            rest = t[len(tens):]
            if rest in NUM_ONES:
                return [tens, rest]
    return None

