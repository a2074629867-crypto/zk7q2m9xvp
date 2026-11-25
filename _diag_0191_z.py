# -*- coding: utf-8 -*-
"""c2_0191 逐词 rel_z：验收版 vs 三档版。验证「重音跑到 much 上」这件事。"""
import json, os, sys
sys.path.insert(0, r"G:\_setup")
from _loop_1123 import word_zs

ID = "c2_0191"
old = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_words.json", encoding="utf-8")).items()}
new = {os.path.basename(k).rsplit(".", 1)[0]: v
       for k, v in json.load(open(r"G:\_setup\_wl_regen1123.json", encoding="utf-8")).items()}

pa = r"G:\_setup\_audio_ch123\out\%s.wav" % ID
pb = r"G:\_setup\_regen_final\%s.wav" % ID
A = word_zs(old[ID], wav=pa)
B = word_zs(new[ID], wav=pb)

print("词数 old=%d new=%d" % (len(A), len(B)))
print("%-14s %8s %8s | %8s %8s" % ("word", "old z", "old s/s", "new z", "new s/s"))
for i in range(min(len(A), len(B))):
    a, b = A[i], B[i]
    flag = ""
    if a["z"] >= 1.6 or b["z"] >= 1.6:
        flag = "  <-- >=1.6"
    print("%-14s %8.2f %8.3f | %8.2f %8.3f%s"
          % (a["w"], a["z"], a["sps"], b["z"], b["sps"], flag))

for tag, W in (("验收版", A), ("三档版", B)):
    top = sorted(W, key=lambda x: -x["z"])[:3]
    print("%s top3: %s" % (tag, ", ".join("%s(%.2f)" % (t["w"], t["z"]) for t in top)))
