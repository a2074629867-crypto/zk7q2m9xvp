# -*- coding: utf-8 -*-
"""用真·ASR 时间戳核对 c2_0191：旧词表到底偏了多少。"""
import json, os, sys
sys.path.insert(0, r"G:\_setup")
import _asr_lib

ID = "c2_0191"
pairs = [("old", r"G:\_setup\_audio_ch123\out\%s.wav" % ID),
         ("new", r"G:\_setup\_regen_final\%s.wav" % ID)]

res = _asr_lib.transcribe([p for _, p in pairs])
for tag, p in pairs:
    r = res[p]
    print("\n=== %s  dur=%.2f  tokens=%d" % (tag, r["dur"], len(r["words"])))
    print("   text:", r["text"][:120])
    for w in r["words"]:
        mark = "   <<<" if w["w"].strip().lower() in ("much", "impressed") else ""
        print("   %-14s %6.2f → %6.2f%s" % (w["w"], w["start"], w["end"], mark))

# 对照旧词表
wl = json.load(open(r"G:\_setup\_wl_words.json", encoding="utf-8"))
wl = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in wl.items()}
print("\n=== 旧词表 (_wl_words.json) 里 c2_0191 的 much/impressed ===")
for w in wl[ID]["words"]:
    if w["w"].strip().lower() in ("much", "impressed"):
        print("   %-14s %6.2f → %6.2f" % (w["w"], w["start"], w["end"]))
