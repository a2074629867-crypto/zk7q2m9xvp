# -*- coding: utf-8 -*-
"""Parakeet(整段+VAD) vs small.en(整段) 逐词交叉核对

两模型独立跑同一段音频，认同=高置信；分歧=需人工裁决的嫌疑点。
"""
import json
import re
import sys
import difflib

D = "G:/GPT-SoVITS/_dataset_v5full"


def norm(t):
    t = t.lower()
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return [w for w in t.split() if w]


PK = json.load(open(D + "/wonder_parakeet.json", encoding="utf-8"))
SE = json.load(open(D + "/asr_full.json", encoding="utf-8"))

pk_words, pk_t = [], []
for s in PK["segments"]:
    ws = norm(s["text"])
    pk_words += ws
    pk_t += [s["start"]] * len(ws)

se_words, se_t = [], []
for s in SE["segments"]:
    if s.get("start") is None:
        continue
    ws = norm(s.get("text", ""))
    se_words += ws
    se_t += [s["start"]] * len(ws)

print("Parakeet %d 词 | small.en %d 词 | 差 %+d" % (len(pk_words), len(se_words), len(pk_words) - len(se_words)))
print("=" * 78)

sm = difflib.SequenceMatcher(None, se_words, pk_words, autojunk=False)
same = sum(b.size for b in sm.get_matching_blocks())
print("完全一致的词 %d | 一致率 %.2f%% (相对 small.en)" % (same, 100.0 * same / max(1, len(se_words))))
print("=" * 78)

ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
print("分歧块 %d 个：\n" % len(ops))
for k, (tag, i1, i2, j1, j2) in enumerate(ops, 1):
    t = se_t[i1] if i1 < len(se_t) else (se_t[-1] if se_t else 0)
    ctx_b = " ".join(se_words[max(0, i1 - 6): i1])
    ctx_a = " ".join(se_words[i2: i2 + 6])
    old = " ".join(se_words[i1:i2]) or "(空)"
    new = " ".join(pk_words[j1:j2]) or "(空)"
    print("%3d. @%7.2fs  %s" % (k, t, tag.upper()))
    print("     上文: ...%s" % ctx_b[-70:])
    print("     small.en : %s" % old)
    print("     Parakeet : %s" % new)
    print("     下文: %s..." % ctx_a[:70])
    print()

# 按类型统计
from collections import Counter
c = Counter(o[0] for o in ops)
print("分歧类型:", dict(c))
