# -*- coding: utf-8 -*-
"""Parakeet 转写定点修正 —— 每条都有 small.en / 上下文佐证

只改"证据充分"的；不确定的写进 --report 供人工裁决，不擅自改。
"""
import argparse
import json
import re

D = "G:/GPT-SoVITS/_dataset_v5full"

# (正则, 替换, 依据)  —— 顺序敏感，先特例后通则
RULES = [
    # Zoe 误识：除 "left his post"（前句是 Grandpa noticed Zoe，指爷爷）外，其余都是 Zoe
    (r"\bAnd so he heard it again\b", "And Zoe heard it again",
     "small.en: 'And Zoe heard it again'；同段 'her big sister' 佐证主角为女性"),
    (r"\bSo he slipped out the back door\b", "Zoe slipped out the back door",
     "small.en: 'Zoe slipped out the back door and onto the cozy wooden deck'"),
    (r"\bSo he closed her eyes\b", "Zoe closed her eyes",
     "small.en: 'Zoe closed her eyes'；'her eyes' 已表明主语为女性"),
    (r"\bSo he drifted off to the soundest of\b", "Zoe drifted off to the soundest of",
     "small.en: 'Zoe drifted off to the soundest of sleep'"),
    # 专名
    (r"\bGrandma said, staring off the stars\b", "Grandpa said, staring off the stars",
     "small.en 上下文：前句 'Well let me see.' 后接 'Grandpa noticed Zoe on the deck'"),
    (r"\bAnd wails under tides\b", "And whales under tides",
     "small.en: 'and whales under tides'；'under tides' 与 whales 搭配"),
    # 代词
    (r"\bAnd looked around your room\b", "And looked around her room",
     "small.en: 'looked around her room'；全书第三人称写 Zoe"),
    # 词形
    (r"\bAnd rap\.\s*In the warmth\b", "And wrapped in the warmth",
     "small.en: 'and wrapped in the warmth'；'rap' 无法与 'In the warmth' 搭配"),
    (r"\bAnd rap\b", "And wrapped",
     "small.en: 'and wrapped in the warmth'"),
]

# 只报告、不改（证据不足，交人工）
REVIEW = [
    (r"I'm again drifting off to an ocean of gratitude",
     "small.en: 'and began drifting off to an ocean of gratitude'；Parakeet: 'I'm again drifting off'"),
    (r"\bA dream\.", "small.en: 'of dreams.'；Parakeet 把 'the sweetest of dreams' 切成 'And the sweetest. A dream.'"),
    (r"^\s*Sh\.?\s*$", "疑似呼气声，small.en 此处无输出"),
    (r"\bsnug the dinosaur\b", "small.en: 'snuck the dinosaur'，但故事里恐龙玩偶名叫 Snug ⇒ Parakeet 可能才是对的"),
    (r"\bSleep\. Sleep\.", "small.en: 'to the soundest of sleep and the sweetest'，Parakeet 重复了 sleep"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=D + "/wonder_v5full_parakeet.list")
    ap.add_argument("--out", default=D + "/wonder_v5full_parakeet_fixed.list")
    ap.add_argument("--log", default=D + "/wonder_parakeet_fixes.json")
    args = ap.parse_args()

    lines = [l.rstrip("\n") for l in open(args.inp, encoding="utf-8") if l.strip()]
    log, nfix = [], 0
    out = []
    for l in lines:
        f, spk, lang, txt = l.split("|", 3)
        orig = txt
        for pat, rep, why in RULES:
            new = re.sub(pat, rep, txt, flags=re.I if pat[0] != "^" else 0)
            if new != txt:
                log.append(dict(file=f, before=txt, after=new, rule=pat, why=why))
                txt = new
                nfix += 1
        out.append("%s|%s|%s|%s" % (f, spk, lang, txt))

    open(args.out, "w", encoding="utf-8").write("\n".join(out) + "\n")

    # 报告项
    flagged = []
    for l in out:
        f, _, _, txt = l.split("|", 3)
        for pat, why in REVIEW:
            if re.search(pat, txt, re.I):
                flagged.append(dict(file=f, text=txt, pattern=pat, why=why))

    json.dump(dict(n_lines=len(out), n_fixes=nfix, fixes=log, flagged=flagged),
              open(args.log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("行数 %d | 应用修正 %d 处 | 待人工裁决 %d 处" % (len(out), nfix, len(flagged)))
    print("写出 %s" % args.out)
    print("写出 %s" % args.log)
    print("\n--- 修正明细 ---")
    for x in log:
        print("  %-46s" % x["file"][-44:])
        print("    前: %s" % x["before"])
        print("    后: %s" % x["after"])
    print("\n--- 待人工裁决 ---")
    for x in flagged:
        print("  [%s] %s" % (x["pattern"][:28], x["text"][:100]))


if __name__ == "__main__":
    main()
