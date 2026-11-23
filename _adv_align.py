# -*- coding: utf-8 -*-
"""_adv_align.py —— 用「原文 + ASR 词时间戳」给每个原词定出时间区间。

为什么需要它：
    Parakeet 会把相邻两词合并成一个 token。N0807 的
        "He thought suddenly of the figures..."
    被识别成
        "He thoughtly   of the figures..."
    `suddenly` 在 ASR 词序列里根本不存在 ⇒ 旧逻辑判成「吞词」，sps=None，
    从而把一个**读得很好**的句子判成不合格（用户听感证实原版没问题）。

做法：
    1. 原文切成词序列（保留标点位置，但只对齐实词）
    2. ASR 词序列（prom 行）与原文做 SequenceMatcher 对齐
    3. opcode == replace 且 k 个原词 → m 个 ASR 词（k>m）时，
       把这 m 个区间按**音节数比例**切给 k 个原词
    4. opcode == delete（原词在 ASR 里彻底没有）→ 用前后已对齐区间的空隙插值；
       空隙为 0 时返回 None（标记 unmeasured，而不是判定失败）

输出：
    [dict(w=原词, key=小写, t0, t1, synthetic=是否拆分/插值得来, unmeasured=bool)]
"""
import difflib
import re


def _norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def _syl(w):
    try:
        import cmudict
        d = cmudict.dict()
        k = _norm(w)
        if k and k in d:
            return max(1, sum(1 for p in d[k][0] if p[-1].isdigit()))
    except Exception:
        pass
    w2 = re.sub(r"[^a-z]", "", w.lower())
    n, prev = 0, False
    for c in w2:
        v = c in "aeiouy"
        if v and not prev:
            n += 1
        prev = v
    return max(1, n if not (w2.endswith("e") and n > 1) else n - 1)


def text_words(text):
    """原文词序列（含标点 token，用 is_word 区分）。"""
    out = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'’-]*|[^\sA-Za-z]+", text):
        w = m.group(0)
        out.append(dict(w=w, key=_norm(w), is_word=bool(_norm(w))))
    return out


def word_spans(text, prom_rows):
    """prom_rows: [(word, t0, t1, prom, bnd)]。返回与原词一一对应的区间列表。"""
    tw = text_words(text)
    exp = [(i, x["key"]) for i, x in enumerate(tw) if x["is_word"]]
    obs = [(j, _norm(r[0])) for j, r in enumerate(prom_rows)]
    obs = [(j, k) for j, k in obs if k]

    spans = [dict(t0=None, t1=None, synthetic=False, unmeasured=False) for _ in tw]
    if not exp or not obs:
        for i, _k in exp:
            spans[i]["unmeasured"] = True
        return spans

    sm = difflib.SequenceMatcher(a=[k for _, k in exp], b=[k for _, k in obs], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                ei = exp[i1 + d][0]
                r = prom_rows[obs[j1 + d][0]]
                spans[ei].update(t0=r[1], t1=r[2], synthetic=False)
        elif tag == "replace":
            k, m = i2 - i1, j2 - j1
            if m == 0:
                continue          # 交给下面的 delete 处理
            block_t0 = prom_rows[obs[j1][0]][1]
            block_t1 = prom_rows[obs[j2 - 1][0]][2]
            if k <= m:            # ASR 更碎：直接按顺序给
                for d in range(k):
                    ei = exp[i1 + d][0]
                    r = prom_rows[obs[j1 + min(d, m - 1)][0]]
                    spans[ei].update(t0=r[1], t1=r[2], synthetic=True)
            else:                 # 原词更多：按音节比例切整块
                syl = [_syl(tw[exp[i1 + d][0]]["w"]) for d in range(k)]
                tot = float(sum(syl)) or 1.0
                acc = 0.0
                for d in range(k):
                    a = block_t0 + (block_t1 - block_t0) * acc / tot
                    acc += syl[d]
                    b = block_t0 + (block_t1 - block_t0) * acc / tot
                    spans[exp[i1 + d][0]].update(t0=a, t1=b, synthetic=True)
        # insert：ASR 多出来的词，忽略

    # delete / 未覆盖：用相邻已定区间的空隙插值
    for i, _k in exp:
        if spans[i]["t0"] is not None:
            continue
        prev_t1 = None
        for j in range(i - 1, -1, -1):
            if spans[j]["t1"] is not None:
                prev_t1 = spans[j]["t1"]
                break
        next_t0 = None
        for j in range(i + 1, len(tw)):
            if spans[j]["t0"] is not None:
                next_t0 = spans[j]["t0"]
                break
        if prev_t1 is not None and next_t0 is not None and next_t0 - prev_t1 > 0.02:
            spans[i].update(t0=prev_t1, t1=next_t0, synthetic=True)
        else:
            spans[i]["unmeasured"] = True
    return spans


def span_of(text, prom_rows, word):
    """取指定词（可重复，取最后一个匹配）的区间。"""
    tw = text_words(text)
    spans = word_spans(text, prom_rows)
    key = _norm(word)
    hit = None
    for i, x in enumerate(tw):
        if x["is_word"] and x["key"] == key:
            hit = i
    if hit is None:
        return None
    s = spans[hit]
    return dict(w=tw[hit]["w"], t0=s["t0"], t1=s["t1"],
                synthetic=s["synthetic"], unmeasured=s["unmeasured"])
