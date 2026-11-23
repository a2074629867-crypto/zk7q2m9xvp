# -*- coding: utf-8 -*-
"""从 v4b 整章切出 RDR 超标段与对照段，做听感校验。"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

d = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
rows = {r["uid"]: r for r in d["rows"]}
seams = d["seams"]

x, sr = sf.read("_chap_ch1_v4b.wav", dtype="float32", always_2d=True); x = x.mean(1)
J = json.load(open("_chap_ch1_v4b.json", encoding="utf-8"))["rows"]
pos, off = 0, {}
for i, r in enumerate(J):
    off[r["uid"]] = (pos, pos + int(round(r["dur"] * sr)))
    pos += int(round(r["dur"] * sr))
    if i < len(J) - 1:
        pos += int(round(r["gap"] * sr))

order = [r["uid"] for r in J]
def cut(uid0, uid1, out, pre=0.15, post=0.30):
    a = max(0, off[uid0][0] - int(pre * sr))
    b = min(len(x), off[uid1][1] + int(post * sr))
    sf.write(out, x[a:b], sr, subtype="PCM_16")
    return (b - a) / sr

# 每组：段内连续单元区间
JOBS = [
    ("A_段94_2.60x", "N0163", "N0167", "_ab/rdr_A.wav"),
    ("B_段64_2.31x", "N0111", "N0115", "_ab/rdr_B.wav"),
    ("C_段45_2.13x", "N0058", "N0062", "_ab/rdr_C.wav"),
    ("D_段6_1.84x",  "N0007", "N0010", "_ab/rdr_D.wav"),
]

# 对照组：找一个多单元段落，所有相邻比都 < 1.15
by = {}
for s in seams:
    by.setdefault(s["pid"], []).append(s["ratio"])
ctrl = None
for pid, rs in sorted(by.items()):
    if len(rs) >= 3 and max(rs) < 1.15:
        ctrl = pid; break
print("对照组段", ctrl, "比值", [round(r, 2) for r in by.get(ctrl, [])])

if ctrl is not None:
    us = [r["uid"] for r in d["rows"] if r["pid"] == ctrl]
    us = [u for u in us if u in off]
    us.sort()
    JOBS.append(("E_段%d_对照<1.15" % ctrl, us[0], us[min(3, len(us)-1)], "_ab/rdr_E.wav"))

for tag, u0, u1, out in JOBS:
    dur = cut(u0, u1, out)
    ws = sum(rows[u]["w"] for u in order[order.index(u0):order.index(u1)+1] if u in rows)
    print("%-18s %-5s..%-5s %6.1fs  %3d 词  %5.0f wpm → %s"
          % (tag, u0, u1, dur, ws, ws/dur*60 if dur else 0, out))
