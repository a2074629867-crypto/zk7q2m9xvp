# -*- coding: utf-8 -*-
"""验证闸4 标签修复：1.2~3.8s 的句子应从 intra_unmeasurable 变为 intra_drift_ok。"""
import sys, os, json
sys.path.insert(0, r"G:/_setup")
sys.path.insert(0, r"G:/_setup/emo_bench")
os.chdir(r"G:/_setup")
import gate_intra as G

for f in ["c1_0020", "c1_0043", "c1_0046", "c1_0002", "c2_0321", "c1_0149"]:
    p = "_audio_ch123/out/%s.wav" % f
    v, info = G.check(p)
    print("%-10s %-5s %-20s drift=%-22s %s" % (
        f, v, info.get("code"), info.get("drift_state"),
        (info.get("why") or "")[:70]))
