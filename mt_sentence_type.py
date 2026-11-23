# -*- coding: utf-8 -*-
"""句型分类：给每个句末边界标上语言学要求的调型方向。

为什么必须有这一层（2026-10-29 实测）：
  闸门原来对所有句子都用「末段上扬 > +3st/s = 缺陷」。
  但 yes-no 疑问（`Can I have the key now, then?`）和反意疑问（`..., can she?`）
  在语言学上**必须升调**，判它上扬等于判对的东西有错。

  实测我们 59 条对白（ch123_final_llm）：
    yes-no/tag/echo（应升）n=7   tail p50 −2.20  上升占 43%
    wh- 疑问（应降）       n=9   tail p50 −3.25  上升占 44%
    陈述句（应降）         n=35  tail p50 −5.38  上升占 17%
  两类疑问的上升比例几乎相同（43% vs 44%）⇒ **模型只认问号，不认句型**。
  所以「该升的没升」是一条真实缺陷，而它只能由读文本的层来判 —— 声学检测器判不了。

分类规则（纯文本，不调模型）：
  wh        why/what/where/when/who/how/which/whose 引出的问句 → 降
  tag       反意疑问尾（will it / can she / shouldn't he / isn't it ...）→ 升
  echo      极短问句（≤3 词）或重复对方用词 → 升
  yesno     其余问句 → 升
  exclam    感叹号 → 降（但幅度可更大）
  stmt      其余 → 降

`list` 不单独成类：列举由 pause_intent 处理，调型仍按陈述降。
"""
import re

WH_WORDS = {'why', 'what', 'where', 'when', 'who', 'whom', 'whose', 'how',
            'which', 'whatever', 'whenever', 'wherever', 'whoever'}

# 反意疑问的尾段模式（问号前最后 2~3 词）
TAG_TAILS = [
    r"\b(will|would|can|could|should|shall|is|are|was|were|do|does|did|"
    r"have|has|had|must|might|may)\s+(it|you|he|she|we|they|i|there)\b",
    r"\b(isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t|didn'?t|"
    r"can'?t|couldn'?t|won'?t|wouldn'?t|shouldn'?t|hasn'?t|haven'?t)\s+"
    r"(it|you|he|she|we|they|there)\b",
]

PUNCT = '.?!'


def split_sents(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def classify(sent):
    """返回 (类型, 期望末段方向 'rise'|'fall'|None)。"""
    s = sent.strip()
    if not s:
        return 'stmt', None
    end = s[-1]
    words = re.findall(r"[A-Za-z']+", s.lower())

    if end == '!':
        return 'exclam', 'fall'
    if end != '?':
        return 'stmt', 'fall'

    # 问号 —— 判定顺序不能反：wh- 信号最强，必须先判。
    # 反例（原版按 tag 先判会全错）：
    #   `Oh, what is it?`  → 尾部 "is it" 命中 tag 模式，但它是 wh- 句
    #   `What have you found?` → 尾部 "have you" 命中，实际 wh-
    #   `How old was he?`  → 尾部 "was he" 命中，实际 wh-
    # 原因：wh- 句的正常语序就是「wh-词 + 助动词 + 主语」，与反意疑问尾段同形。
    head = words[:2]
    if any(w in WH_WORDS for w in head):
        return 'wh', 'fall'
    if len(words) <= 3:
        return 'echo', 'rise'
    tail = ' '.join(words[-4:])
    for pat in TAG_TAILS:
        if re.search(pat, tail):
            return 'tag', 'rise'
    return 'yesno', 'rise'


def label_text(text):
    """把一段文本切成句，逐句给类型。返回 [(句子, 类型, 期望方向)]。"""
    out = []
    for s in split_sents(text):
        t, d = classify(s)
        out.append((s, t, d))
    return out


def corpus_stats(texts):
    """texts: {key: text}，返回 {key: [(句, 类型, 方向)]} 与汇总。"""
    per = {}
    from collections import Counter
    c = Counter()
    for k, t in texts.items():
        rows = label_text(t)
        per[k] = rows
        for _, ty, _ in rows:
            c[ty] += 1
    return per, dict(c)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, r'G:/_setup')
    from ch123_plan import PLAN, INNER

    T = {'L%03d' % i: t for i, _, _, t in PLAN}
    T.update({'I%02d' % i: t for i, (_, _, _, t) in enumerate(INNER)})
    per, summ = corpus_stats(T)
    print('对白句型分布:', summ)
    print()
    for k in sorted(per):
        for s, ty, d in per[k]:
            if ty != 'stmt':
                print('  %-5s %-7s → %-4s  %s' % (k, ty, d, s[:70]))
