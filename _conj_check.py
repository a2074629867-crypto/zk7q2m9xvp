# -*- coding: utf-8 -*-
"""_conj_check.py —— 验证「连词前的长停」到底是原文逗号，还是真的无标点停顿。

对 and/but/so/as/that 前面的每个 >=0.6s 停顿，输出三元组：
  [前词] | [间隙] | [连词] ... 后面 4 个词
并标注前词是否带标点。
"""
import json
import re
from collections import Counter

import numpy as np
import soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
SR = 32000


def norm(w):
    return re.sub(r"^[^\w']+|[^\w']+$", "", w.lower())


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
mids = [(a + b) / 2 for a, b, _ in words]

gaps = []
for k in range(1, len(segs)):
    g0, g1 = segs[k - 1][1], segs[k][0]
    dur = g1 - g0
    if dur < 0.06:
        continue
    gmid = (g0 + g1) / 2
    lo, hi = 0, len(mids)
    while lo < hi:
        md = (lo + hi) // 2
        if mids[md] <= gmid:
            lo = md + 1
        else:
            hi = md
    pi, ni = lo - 1, lo
    if pi < 0 or ni >= len(words):
        continue
    gaps.append(dict(dur=round(dur, 3), pi=pi, ni=ni))

TARGETS = ["and", "but", "so", "as", "that", "then", "because", "which"]
print("=" * 78)
for tgt in TARGETS:
    rows = [g for g in gaps if norm(words[g["ni"]][2]) == tgt]
    if not rows:
        continue
    longg = [g for g in rows if g["dur"] >= 0.6]
    withp = [g for g in longg if re.search(r"[,\.\?;:!]$", words[g["pi"]][2])]
    print("\n### %s：共 %d 个前停顿 | 长停 %d（其中前词带标点 %d，无标点 %d）"
          % (tgt, len(rows), len(longg), len(withp), len(longg) - len(withp)))
    for g in rows:
        pi, ni = g["pi"], g["ni"]
        ctx_before = " ".join(w for _, _, w in words[max(0, pi - 5):pi + 1])
        ctx_after = " ".join(w for _, _, w in words[ni:ni + 5])
        mark = "P" if re.search(r"[,\.\?;:!]$", words[pi][2]) else "-"
        print("  [%s] %5.2fs  ...%s ⟦%s⟧ %s..." % (mark, g["dur"], ctx_before[-38:], tgt, ctx_after[:44]))
