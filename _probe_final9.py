# -*- coding: utf-8 -*-
"""核对「剪停顿 + 填底噪」前后哪些条目的 w2v 覆盖率掉了，并判断是真空损失还是度量噪声。"""
import io
import json
import sys

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG
import _pick52 as PK

post = {r["id"]: r for r in json.load(io.open("_align_final9.json", encoding="utf-8"))}
# 剪前逐条：从 final9 目录重新取 w2v？没有存，用 merge 的 cov（老匹配器）
# → 这里直接对比「剪后」与「live 原始」，因为 live 的 align 也存了 w2v_text
live = {r["id"]: r for r in json.load(io.open("_align_live.json", encoding="utf-8"))}
plan = CG.load_plan()
summ = json.load(io.open("_final9_summary.json", encoding="utf-8"))

rows = []
for i, r in post.items():
    cov = r.get("w2v_cov") or 0
    if cov >= 0.85:
        continue
    lv = live.get(i) or {}
    lcov = lv.get("w2v_cov") or 0
    rows.append((cov, i, lcov, (r.get("w2v_text") or "")[:44],
                 (plan.get(i, {}).get("text") or "")[:44],
                 summ.get(i, {}).get("kind")))
rows.sort()
print("剪后仍 <0.85 的 %d 条（live 覆盖率 / 剪后 w2v / 原文 / 采用来源）:" % len(rows))
for cov, i, lcov, hyp, gold, kind in rows:
    print("  %-9s %.2f (live %.2f) %-46s | %-46s %s" % (i, cov, lcov, hyp, gold, kind))
