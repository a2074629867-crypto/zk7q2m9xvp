# -*- coding: utf-8 -*-
"""ASR 覆盖率（连字符拆开口径）。"""
import json, re, os, difflib, sys
sys.path.insert(0, "D:/py_libs")
import numpy as np

S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]

def analyze(f):
    d = json.load(open(f, encoding="utf-8"))
    out = {}
    for path, v in d.items():
        uid = os.path.basename(path)[:-4]
        if uid not in S:
            continue
        ref = [x.lower() for x in re.findall(r"[A-Za-z]+", S[uid]["text"])]
        hyp = [x.lower() for w in v.get("words", []) for x in re.findall(r"[A-Za-z]+", w["w"])]
        if not ref:
            continue
        sm = difflib.SequenceMatcher(a=ref, b=hyp)
        miss, ok = [], 0
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                ok += i2 - i1
            else:
                miss += ref[i1:i2]
        out[uid] = dict(cov=round(ok / len(ref), 4), n=len(ref), miss=miss)
    return out

for tag, f in (("s42", "_asr_trim_s42.json"), ("s1234", "_asr_trim_s1234.json")):
    D = analyze(f)
    json.dump(D, open("_asr_cov_%s.json" % tag, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c = np.array([v["cov"] for v in D.values()])
    print("%-6s n=%3d  p10 %.3f p25 %.3f p50 %.3f 均值 %.3f  完美 %d/%d  <95%% %d 条"
          % (tag, len(c), np.percentile(c, 10), np.percentile(c, 25), np.median(c),
             c.mean(), int((c == 1).sum()), len(c), int((c < 0.95).sum())))
    bad = sorted(D.items(), key=lambda kv: kv[1]["cov"])[:8]
    for u, v in bad:
        print("     %-6s cov %.2f (%d词) 漏 %s" % (u, v["cov"], v["n"], v["miss"]))
    print()
