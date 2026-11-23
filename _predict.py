# -*- coding: utf-8 -*-
"""预测端：文本 → 词级韵律方案（prominence 0/1/2 + boundary 0/2）。

只用封闭类虚词表 + 句内位置，零训练、零依赖。
在 Helsinki LibriTTS 测试集（5195 句 / 90063 词）上的实测：
  二分类（重/不重）F1 78.7%，句内 top1 命中 63.8%

输出格式（与 WordVoice 的五属性对齐，便于后续换更复杂的预测器）：
  {
    "words": [
      {"w": "grandmother", "idx": 5, "content": true,
       "prom": 2,            # 0 不重 / 1 重 / 2 核心重音
       "bnd": 0,             # 0 无停顿 / 2 句末
       "why": "long+content"}
    ],
    "n_word": 14,
    "focus": [5, 13]         # 标为 2 的词的下标
  }

用法：
  python _predict.py "Three months ago, his grandmother died."
  python _predict.py --json            # 从 stdin 读文本
  python _predict.py --plan mt_plan3b.json --out _pred_plan.json
"""
import argparse
import json
import re
import sys

# 英语封闭类虚词：这些词在无对比焦点时几乎不承载重音
FUNC = set("""
a an the
of in to for with on at by from up about into over after beneath under above
across along among around before behind below beside between beyond down during
except inside near off onto outside past since through throughout till toward
towards upon within without
and but or nor so yet because although though while whereas if unless until
when whenever where wherever whether that than as lest once
i me my mine myself you your yours yourself he him his himself she her hers
herself it its itself we us our ours ourselves they them their theirs themselves
this these those who whom whose which what whatever whoever
am is are was were be been being have has had having do does did done doing
will would shall should can could may might must ought need dare used
some any no every each either neither both all few many much more most several
such another other same
there here not
s n't 's
""".split())

AMBIG = set("one two three four five six seven eight nine ten half both all".split())
NEG = set("not n't never no nothing none nobody nowhere neither nor".split())
# 提示对比/强调的副词：出现时该词本身倾向于重读
EMPH = set("only even just still already almost nearly quite rather very too again".split())
# 常见但不在上表的虚词（补充）
EXTRA_FUNC = set("""
then when while as if so than such own same else
""".split())

SENT_END = set(".!?")
CLAUSE_SEP = set(",;:")

# 默认保守：核心重音只给句末实词 / 否定 / 强调副词。
# 打开后把长词（>=7 字符）也提到 2，在 Helsinki 集上可把 top1 命中从 56.6% 拉到 63.8%。
AGGRESSIVE = False


def is_func(w):
    lw = w.lower().strip(".,;:!?\"'()—-")
    if not lw:
        return True
    # 兼类词按内容词处理（数字、both/all 可作限定词也可重读）
    if lw in AMBIG:
        return False
    if lw in FUNC or lw in EXTRA_FUNC:
        return True
    # 两字母功能词（be/of/it/we 等），但保留可重读的
    if len(lw) <= 2 and lw not in ("ox", "ax", "go"):
        return True
    return False


def tokenize(text):
    """保留标点作为独立 token（boundary 需要）。"""
    return re.findall(r"[A-Za-z0-9'’\-]+|[.,;:!?]", text)


def predict(text):
    toks = tokenize(text)
    # 有效词索引（非标点）
    words = []
    for t in toks:
        if t in SENT_END or t in CLAUSE_SEP:
            words.append(dict(w=t, content=None, punct=True))
        else:
            words.append(dict(w=t, content=not is_func(t), punct=False))

    widx = [i for i, x in enumerate(words) if not x["punct"]]
    n = len(widx)
    if n == 0:
        return dict(words=[], n_word=0, focus=[])

    first_ct = next((i for i in widx if words[i]["content"]), -1)
    last_ct = next((i for i in reversed(widx) if words[i]["content"]), -1)

    # 句子最后位置（用于句末判断）
    last_w = widx[-1]

    for i, x in enumerate(words):
        if x["punct"]:
            if x["w"] in SENT_END:
                x["prom"] = None
                x["bnd"] = 2
                x["why"] = "sentence-end"
            elif x["w"] in CLAUSE_SEP:
                x["prom"] = None
                x["bnd"] = 1
                x["why"] = "clause-sep"
            else:
                x["prom"] = None
                x["bnd"] = 0
            continue

        lw = x["w"].lower()
        why = []
        if not x["content"]:
            p = 0
            why.append("func")
        else:
            p = 1
            why.append("content")
            if lw in NEG:
                p = 2
                why.append("neg")
            if lw in EMPH:
                p = 2
                why.append("emph")
            if i == last_ct:
                p = 2
                why.append("end-focus")
            if i == first_ct and n > 4:
                p = max(p, 1)
                why.append("onset")
            # 长词只在 aggressive 模式提到 2；默认保持 1
            if AGGRESSIVE and len(lw) >= 7:
                p = max(p, 2)
                why.append("long")
        # boundary：词后紧跟标点时由标点承担，这里只标 0
        x["prom"] = p
        x["bnd"] = 0
        x["why"] = "+".join(why)

    focus = [i for i in widx if words[i]["prom"] == 2]
    # 若没有任何 2，退化为最后一个内容词
    if not focus and last_ct >= 0:
        words[last_ct]["prom"] = 2
        words[last_ct]["why"] += "+fallback"
        focus = [last_ct]

    return dict(words=words, n_word=n, focus=focus,
                text=text, n_plan=len(text.split()))


def brief(r):
    L = []
    for x in r["words"]:
        if x["punct"]:
            L.append("%s[b%d]" % (x["w"], x["bnd"]))
        else:
            L.append("%s/%d" % (x["w"], x["prom"]))
    return " ".join(L)


def main():
    global AGGRESSIVE
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--aggressive", action="store_true",
                    help="长词也算核心重音（top1 命中更高，但标 2 的词更多）")
    a = ap.parse_args()
    AGGRESSIVE = a.aggressive

    if a.plan:
        plan = json.load(open(a.plan, encoding="utf-8"))
        out = {}
        for u in plan:
            out[u["id"]] = predict(u["text"])
        if a.out:
            json.dump(out, open(a.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print("写入 %s（%d 单元）" % (a.out, len(out)))
        else:
            print(json.dumps(out, ensure_ascii=False)[:2000])
        return

    text = " ".join(a.text) if a.text else sys.stdin.read()
    r = predict(text)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("原文:", text.strip())
        print("词数:", r["n_word"], " 核心重音:", [r["words"][i]["w"] for i in r["focus"]])
        print(brief(r))


if __name__ == "__main__":
    main()
