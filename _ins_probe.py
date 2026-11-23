# -*- coding: utf-8 -*-
"""查交付版里「多念了词」的条目（参考文本泄漏 / LEAD_REF 复读）。

判据：wav2vec2 贪心解码出的词数明显多于原文词数（gold 有 6 个词、hyp 有 14 个）。
这不是吞字，是**多字**，只有不带语言模型的贪心解码能看出来 ——
Parakeet / whisper 会把多出来的部分“修”成通顺句子，因而完全查不出。
"""
import io
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG
import _pick52 as PK

plan = CG.load_plan()
al = json.load(io.open("_align_deliver.json", encoding="utf-8"))

rows = []
for r in al:
    rid = r["id"]
    gold = PK.norm_words((plan.get(rid) or {}).get("text") or "")
    hyp = PK.norm_words(r.get("w2v_text") or "")
    if not gold:
        continue
    extra = len(hyp) - len(gold)
    if extra >= 3 and len(hyp) > len(gold) * 1.4:
        rows.append((extra, rid, len(gold), len(hyp), (r.get("w2v_text") or "")[:70],
                     (plan.get(rid, {}).get("text") or "")[:40]))
rows.sort(reverse=True)
print("疑似多念（插入 ≥3 词且超原文 1.4 倍）: %d 条" % len(rows))
for ex, rid, ng, nh, hyp, gold in rows:
    print("  %-9s +%-2d 词  原文 %d → 解码 %d" % (rid, ex, ng, nh))
    print("       gold: %s" % gold)
    print("       w2v : %s" % hyp)
