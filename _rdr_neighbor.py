# -*- coding: utf-8 -*-
"""统一口径：相邻片段（不是组内任意对）的语速比分布。我们 vs 马修。"""
import sys, json, os, re
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]
PARA = {r["uid"]: r.get("pid") for r in json.load(open("_ch1_unit_para.json", encoding="utf-8"))}
PAD = 0.25
def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))

ours = []
for uid, pid in PARA.items():
    p = os.path.join("_mt_final_raw_trim", uid + ".wav")
    if not os.path.exists(p) or pid is None:
        continue
    i = sf.info(p); eff = i.frames / i.samplerate - PAD
    w = nwords(S[uid]["text"])
    if w < 3 or eff < 0.4:
        continue
    ours.append((pid, uid, w, eff, w / eff * 60))

def report(tag, seq):
    if not seq:
        print(tag, "无数据"); return
    a = np.array(seq)
    print("%-26s n=%2d  p50 %.2f  p75 %.2f  p90 %.2f  max %.2f  超1.5 %.0f%%"
          % (tag, len(a), np.median(a), np.percentile(a, 75),
             np.percentile(a, 90), a.max(), 100 * (a > 1.5).mean()))

# 我们：同段落内相邻单元
ratios, ratios8 = [], []
by = {}
for pid, uid, w, eff, r in ours:
    by.setdefault(pid, []).append((uid, w, r))
for pid, lst in by.items():
    for k in range(len(lst) - 1):
        a, b = lst[k][2], lst[k + 1][2]
        ratios.append(max(a, b) / min(a, b))
        if lst[k][1] >= 8 and lst[k + 1][1] >= 8:
            ratios8.append(max(a, b) / min(a, b))
report("我们 段内相邻单元", ratios)
report("我们 段内相邻 w>=8", ratios8)

# 马修：相邻句
M = json.load(open("_matt_sents.json", encoding="utf-8"))
ms = []
for s in M:
    if len(s) < 3:
        continue
    eff = s[-1][1] - s[0][0]
    if eff < 0.4:
        continue
    ms.append((len(s), len(s) / eff * 60))
mr = [max(ms[k][1], ms[k+1][1]) / min(ms[k][1], ms[k+1][1]) for k in range(len(ms) - 1)]
mr8 = [max(ms[k][1], ms[k+1][1]) / min(ms[k][1], ms[k+1][1])
       for k in range(len(ms) - 1) if ms[k][0] >= 8 and ms[k+1][0] >= 8]
report("马修 相邻句", mr)
report("马修 相邻句 w>=8", mr8)
