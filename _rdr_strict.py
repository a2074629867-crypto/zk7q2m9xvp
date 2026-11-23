# -*- coding: utf-8 -*-
"""RDR 门槛敏感性：词数/有效时长门槛变化时 RDR 怎么动。"""
import sys, json, os, re, itertools
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf
S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]
PARA = {r["uid"]: r.get("pid") for r in json.load(open("_ch1_unit_para.json", encoding="utf-8"))}
PAD = 0.25
def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))
cache = {}
for uid in PARA:
    p = os.path.join("_mt_final_raw_trim", uid + ".wav")
    if os.path.exists(p):
        i = sf.info(p); cache[uid] = i.frames / i.samplerate
for minw, mineff in [(3,0.4),(4,0.6),(5,0.8),(5,1.0),(6,1.0),(8,1.2)]:
    rows = []
    for uid, pid in PARA.items():
        if uid not in cache: continue
        eff = cache[uid] - PAD; w = nwords(S[uid]["text"])
        if w < minw or eff < mineff: continue
        rows.append((uid, pid, w/eff*60))
    g = {}
    for uid, pid, r in rows:
        if pid is not None: g.setdefault(pid, []).append((uid, r))
    bad = tot = 0; mx_all = 0
    for pid, lst in g.items():
        if len(lst) < 2: continue
        tot += 1
        m = max(max(a[1],b[1])/min(a[1],b[1]) for a,b in itertools.combinations(lst,2))
        mx_all = max(mx_all, m)
        if m > 1.5: bad += 1
    print("门槛 w>=%d eff>=%.1fs : 单元 %3d  组 %2d  不连续 %2d  RDR %.3f  最大比 %.2f"
          % (minw, mineff, len(rows), tot, bad, bad/tot if tot else 0, mx_all))
