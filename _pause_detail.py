# -*- coding: utf-8 -*-
"""_pause_detail.py —— 停顿规则的细节分析（补 mc_pause_rules.py）

回答四个问题：
  1. 逗号停顿受什么影响？（后接连词 / 前子句长度 / 枚举）
  2. 句号停顿受什么影响？（后句以 And/But/So 开头 / 后句长度 / 段落）
  3. 连词「后面」停不停？（and 后 / but 后 / so 后）
  4. 超长停顿（>=2.3s）出现在哪 → 段落边界规则
"""
import bisect
import json
import re
from collections import Counter, defaultdict

import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
SR = 32000

CONJ = set("and but or nor yet so for because when while if though although unless "
           "until since as than that which who whom whose where whether then".split())
ART = set("the a an".split())
PREP = set("of in on at to with from by about into over under through between across "
           "around like without within upon toward towards against along behind beyond "
           "during except inside outside past off onto unto per via".split())
PRON = set("i you he she it we they me him her us them my your his its our their this "
           "these those what something someone anything anyone everyone everything "
           "nothing nobody anybody".split())
AUX = set("is are was were be been being am do does did have has had will would can "
          "could shall should may might must".split())


def norm(w):
    return re.sub(r"^[^\w']+|[^\w']+$", "", w.lower())


def stats(v):
    if not v:
        return None
    a = np.array(v, float)
    return "n=%d 中位%.2f p25%.2f p75%.2f p90%.2f" % (
        len(a), np.median(a), np.percentile(a, 25), np.percentile(a, 75), np.percentile(a, 90))


def vad_segments():
    x, sr = sf.read(MASTER, dtype="float64", always_2d=True)
    x = x.mean(1)
    hop = int(SR * 0.010)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < 8:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < 12:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return segs


segs = vad_segments()
d = json.load(open(WORDS, encoding="utf-8"))
words = []
for s in d["slices"]:
    for t0, t1, w in s.get("words", []):
        words.append((float(t0), float(t1), w))
words.sort(key=lambda t: t[0])
t0s = [a for a, b, _ in words]

gaps = []
for k in range(1, len(segs)):
    g0, g1 = segs[k - 1][1], segs[k][0]
    if g1 - g0 < 0.06:
        continue
    pi = bisect.bisect_right(t0s, g0) - 1
    ni = bisect.bisect_left(t0s, g1)
    if pi < 0 or ni >= len(words) or ni <= pi:
        continue
    gaps.append(dict(dur=round(g1 - g0, 3), pi=pi, ni=ni))

P = re.compile(r"([,\.\?;:!]+)\s*$")


def punct_of(w):
    m = P.search(w)
    return m.group(1)[0] if m else None


commas = [g for g in gaps if punct_of(words[g["pi"]][2]) == ","]
periods = [g for g in gaps if punct_of(words[g["pi"]][2]) == "."]

print("=" * 70)
print("【1】逗号停顿 n=%d  %s" % (len(commas), stats([g["dur"] for g in commas])))

# 1a 后接词类别
by = defaultdict(list)
for g in commas:
    nw = norm(words[g["ni"]][2])
    if nw in CONJ:
        by["连词"].append(g["dur"])
    elif nw in ART:
        by["冠词"].append(g["dur"])
    elif nw in PREP:
        by["介词"].append(g["dur"])
    elif nw in PRON:
        by["代词"].append(g["dur"])
    else:
        by["实词/其他"].append(g["dur"])
print("  按后接词：")
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print("    %-8s %s" % (k, stats(v)))

# 1b 前子句长度（从上个句号/逗号到本逗号之间的词数）
def clause_len(gi):
    p = gi["pi"]
    k = p - 1
    while k >= 0 and punct_of(words[k][2]) is None:
        k -= 1
    return p - k


by = defaultdict(list)
for g in commas:
    L = clause_len(g)
    b = "<=5" if L <= 5 else "6-10" if L <= 10 else "11-16" if L <= 16 else ">16"
    by[b].append(g["dur"])
print("  按前子句词数：")
for k in ["<=5", "6-10", "11-16", ">16"]:
    if k in by:
        print("    %-6s %s" % (k, stats(by[k])))

print("\n【2】句号停顿 n=%d  %s" % (len(periods), stats([g["dur"] for g in periods])))
by = defaultdict(list)
for g in periods:
    nw = norm(words[g["ni"]][2])
    if nw in ("and", "but", "so", "yet", "then", "or"):
        by["后句以连词开头"].append(g["dur"])
    elif nw in ART:
        by["后句以冠词开头"].append(g["dur"])
    elif nw in PRON:
        by["后句以代词开头"].append(g["dur"])
    else:
        by["其他"].append(g["dur"])
print("  按后句开头：")
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print("    %-14s %s" % (k, stats(v)))

by = defaultdict(list)
for g in periods:
    L = g["ni"]
    k = L
    while k < len(words) and punct_of(words[k][2]) is None:
        k += 1
    n = k - L + 1
    b = "<=6" if n <= 6 else "7-12" if n <= 12 else "13-20" if n <= 20 else ">20"
    by[b].append(g["dur"])
print("  按后句长度：")
for k in ["<=6", "7-12", "13-20", ">20"]:
    if k in by:
        print("    %-6s %s" % (k, stats(by[k])))

print("\n【3】超长停顿 >=2.3s（疑似段落边界）n=%d"
      % len([g for g in gaps if g["dur"] >= 2.3]))
for g in [g for g in gaps if g["dur"] >= 2.3]:
    print("    %5.2fs  ...%s ⟦⟧ %s..." %
          (g["dur"], words[g["pi"]][2][-16:], " ".join(w for _, _, w in words[g["ni"]:g["ni"] + 5])[:42]))

print("\n【4】连词「后面」的停顿（prev = 连词）")
for c in ["and", "but", "so", "then", "that", "as", "because"]:
    v = [g["dur"] for g in gaps if norm(words[g["pi"]][2]) == c]
    if v:
        print("  %-8s n=%3d  %s" % (c, len(v), stats(v)))
    else:
        print("  %-8s n=  0" % c)

print("\n【5】句首/句尾位置：第一个词后、最后一个词前")
# 句内位置：间隙前面有几个词（自上个句号起）
print("\n【6】逗号位置在句中还是句尾（后接词是否仍属同句）")
tail = [g for g in commas if g["ni"] >= len(words)]
print("  无")
