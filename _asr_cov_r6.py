# -*- coding: utf-8 -*-
"""_asr_cov_r6.py —— 对 r6 的 25 条候选做 ASR 覆盖率，判「高 wpm 是截断还是真快」。

判据（与 r5 截断样本同口径）：
  cov = 命中词数 / 文本词数（连字符拆开，大小写无关，difflib 对齐）
  截断的典型特征：cov < 0.95 且缺失词全部在句尾。
只用 asr_venv 跑（G:/Python310 没有 onnx_asr）。
"""
import json
import re
import sys
import difflib

sys.path.insert(0, "G:/_setup")
import _asr_lib

CAND = "G:/_setup/_dlg_plan_r6_cand.jsonl"
OUT = "G:/_setup/_asr_cov_r6.json"


def words_of(t):
    t = t.replace("\u2018", " ").replace("\u2019", "'")
    return [x.lower() for x in re.findall(r"[A-Za-z']+", t)]


def cov_of(ref, hyp):
    sm = difflib.SequenceMatcher(a=ref, b=hyp)
    ok, miss = 0, []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            ok += i2 - i1
        else:
            miss += ref[i1:i2]
    return (ok / len(ref) if ref else 1.0), miss


rows = [json.loads(l) for l in open(CAND, encoding="utf-8")]
res = _asr_lib.transcribe([r["path"] for r in rows])

out = []
print("%-9s %3s %6s %5s %5s  %s" % ("id", "词", "dur", "wpm", "cov", "漏词"))
for r in rows:
    v = res.get(r["path"]) or {}
    ref = words_of(r["text"])
    hyp = [w.lower() for w in re.findall(r"[A-Za-z']+", v.get("text") or "")]
    c, miss = cov_of(ref, hyp)
    dur = v.get("dur") or 0
    wpm = len(ref) / dur * 60 if dur else 0
    out.append(dict(id=r["id"], n=len(ref), dur=round(dur, 2), wpm=round(wpm),
                    cov=round(c, 3), miss=miss, hyp=v.get("text")))
    print("%-9s %3d %6.2f %5.0f %5.3f  %s" % (r["id"], len(ref), dur, wpm, c, miss))

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
bad = [x for x in out if x["cov"] < 0.95]
print("\n总 %d 条；cov<0.95 的 %d 条：%s" % (len(out), len(bad), [x["id"] for x in bad]))
