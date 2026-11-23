# -*- coding: utf-8 -*-
"""用 emotion2vec 直接判 59 条已交付对白，与 LR 迁移结果互相印证。"""
import json, os, sys
import numpy as np
sys.path.insert(0, ".")
import ser as S

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "out", "book_judge.json"), encoding="utf-8"))["rows"]
MAP = {"calm": "neutral", "sad": "sad", "happy": "happy"}
CN = {"开心/happy": "happy", "难过/sad": "sad", "生气/angry": "angry",
      "中立/neutral": "neutral", "恐惧/fearful": "afraid",
      "厌恶/disgusted": "disgusted", "吃惊/surprised": "surprised",
      "其他/other": "other", "<unk>": "unk"}
M = S.E2V(model="G:/_setup/models/ms/iic/emotion2vec_plus_large")
WAV = os.path.join("G:/_setup", "ch123_final")
y, p, who, dur = [], [], [], []
import collections
conf = collections.Counter()
for r in rows:
    g = MAP.get((r.get("emo") or "").lower())
    if not g:
        continue
    w = os.path.join(WAV, r["id"] + ".wav")
    if not os.path.exists(w):
        continue
    s = M.score(w)
    lab = CN.get(s["_top"], s["_top"])
    y.append(g); p.append(lab); who.append(r["who"]); dur.append(r["dur"])
    conf[lab] += 1
print("n=%d" % len(y))
print("accuracy = %.3f" % np.mean([a == b for a, b in zip(y, p)]))
print("majority 基线 = %.3f" % (max(collections.Counter(y).values()) / len(y)))
labels = ["happy", "sad", "neutral"]
print("混淆（行=标注，列=e2v）")
print("  %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
for c in labels:
    row = [sum(1 for a, b in zip(y, p) if a == c and b == k) for k in labels]
    print("  %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in row), sum(row)))
print("e2v 判定分布：%s" % dict(conf))
for w in sorted(set(who)):
    idx = [i for i, x in enumerate(who) if x == w]
    print("  角色 %s n=%2d accuracy=%.3f" % (w, len(idx),
          np.mean([y[i] == p[i] for i in idx])))
print("时长：中位 %.2fs，<3s 占 %.0f%%" % (np.median(dur), 100 * np.mean([d < 3 for d in dur])))
