# -*- coding: utf-8 -*-
"""为「多念词」的 5 条找替代：在 live / emo / role 里挑一个既无插入、覆盖率又高的。"""
import io
import json
import os
import shutil
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG
import _pick52 as PK

IDS = ["c2_0445", "c1_0046", "c1_0149", "c2_0430", "c2_0404"]
plan = CG.load_plan()

live = {r["id"]: r for r in json.load(io.open("_align_live.json", encoding="utf-8"))}
camp = {}
for r in json.load(io.open("_align_camp9.json", encoding="utf-8")):
    camp[os.path.basename(r["wav"])[:-4]] = r

for rid in IDS:
    gold = PK.norm_words(plan[rid].get("text") or "")
    print("== %s  gold=%d 词  %s" % (rid, len(gold), (plan[rid].get("text") or "")[:50]))
    cands = []
    lv = live.get(rid)
    if lv:
        cands.append(("live", "_bak_deliver_1121/plain/%s.wav" % rid, lv))
    for tag, r in camp.items():
        if tag.split("__")[0] == rid:
            cands.append((tag.split("__")[1], "_sweep/camp9/%s.wav" % tag, r))
    for kind, path, r in cands:
        hyp = PK.norm_words(r.get("w2v_text") or "")
        extra = len(hyp) - len(gold)
        cov = r.get("w2v_cov") or 0
        print("   %-6s cov=%.2f  +%-2d 词  %s" % (kind, cov, extra, (r.get("w2v_text") or "")[:60]))
        print("          %s" % path)
