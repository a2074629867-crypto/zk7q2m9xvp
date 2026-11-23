# -*- coding: utf-8 -*-
"""「读全了吗」检测：对白七闸里没有这一维 —— 闸全 PASS 也可能整句只念了后半截。

为什么需要它（2026-11-15 18:5x 实测）：
  `c1_0034`（Thomas 委屈，"I wouldn't do any harm, there, why can't I go?"）
  交付版 4.16s、tech/emotion/intra/nat 全 PASS，但 ASR 只认出 "Why can't I go?" ——
  前 2.5s 是糊的（begging 参考 MOS 0.836 的残片质感），whisper 一个词都听不出。
  反过来，换参考生成的候选 2.88s 却完整读出 10 个词。
  ⇒ 只看时长会把「读全但正常语速」判成退化、把「糊掉一半」判成正常。

判据：ASR 词序列对原文的词召回率（去掉标点、小写、按序做子序列匹配），
  召回 < 0.80 记 `not_full`。这个数只用来**比较**同一条的现役与候选，
  不单独定生死（whisper 对气声/耳语的识别率本身有限）。

用法：
  python _read_full.py --ids c1_0034,c2_0437                 # 只测现役
  python _read_full.py --ids c1_0034 --cand _sweep/cand10n   # 现役 + 候选
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AUD = os.path.join(HERE, "_audio_ch123", "out")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")


def norm_words(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^A-Za-z']+", " ", s)
    return [w.lower().strip("'") for w in s.split() if w.strip("'")]


def recall(ref, hyp):
    """按序子序列匹配的召回率（whisper 会漏词/拆词，不做严格对齐）。"""
    if not ref:
        return 0.0
    i = 0
    hit = 0
    for w in hyp:
        # 允许 hyp 词包含 ref 词（"can't" vs "cannot" 之类）
        while i < len(ref):
            if ref[i] == w or ref[i] in w or w in ref[i]:
                hit += 1
                i += 1
                break
            i += 1
        else:
            break
    return hit / float(len(ref))


def asr(p):
    from transplant_prosody2 import word_times
    return [t for _a, _b, t in word_times(p)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--cand", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l)
            plan[o["id"]] = o

    rows = []
    for rid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        ref = norm_words(plan[rid].get("text") or "")
        files = [("现役", os.path.join(AUD, rid + ".wav"))]
        if a.cand:
            for p in sorted(glob.glob(os.path.join(a.cand, "%s__s*.wav" % rid))):
                files.append((os.path.basename(p)[:-4].rsplit("__s", 1)[1], p))
        print("== %s  %s/%s  原文 %d 词：%s"
              % (rid, plan[rid].get("who"), plan[rid].get("emo"), len(ref), " ".join(ref)))
        for tag, p in files:
            if not os.path.exists(p):
                print("   %-8s 缺文件 %s" % (tag, p))
                continue
            # ★ 必须先把 ASR 词做同样归一化（whisper 返回 " Why" 带前导空格和标点），
            #   否则逐词比较全不相等，召回恒为 0 —— 第一版就栽在这，10/10 词也报 0.00。
            hyp = norm_words(" ".join(asr(p)))
            r = recall(ref, hyp)
            print("   %-8s 召回 %.2f  ASR %d 词：%s"
                  % (tag, r, len(hyp), " ".join(hyp)[:90]))
            rows.append(dict(id=rid, tag=tag, path=p, recall=round(r, 3),
                             n_asr=len(hyp), hyp=" ".join(hyp)))
    if a.out:
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
