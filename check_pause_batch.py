# -*- coding: utf-8 -*-
"""校验人工标注批次的完整性（不许漏、不许串位、不许自创 bid）。"""
import collections
import json
import sys

CTX = "G:/_setup/_pause_ctx.jsonl"

# ★★★ 旁白三档（2026-11-11 第三次校准，这次有实证支撑）
#
# 依据：skill dots-tts-dubbing §18.33 / §18.34（2026-10-30 三方盲标定案）
#   三方 = main / Hunyuan4-preview / DS4.1F，盲标（不给时长，防锚定），60 条
#   全档 Kappa **0.841**、全一致率 **85%**（第一轮 5 档只有 0.459 / 48%）
#
# 判据只有一句：**删掉逗号后半，前半还完整吗？**
#   不完整（后半是必需补足）→ inner     median 0.51s (n=15)
#   完整（并列/状语/同位/新成分）→ bound  median 1.135s (n=24)
#   句子结束 → clause                   median 1.695s (n=12)
#   AUC(bound>inner)=0.840 / AUC(clause>bound)=0.738
#
# ⚠ 两个被我误用的档位（来自对白 _annot_task.md，旁白不存在）：
#   · **旁白没有 drop**：三方判出的 drop 实测中位 1.35~1.53s，而 drop 本该"几乎不停"。
#     根因是判据「连续短项列举→drop」被滥用 —— 马修在列举项之间照停，且停得和句末一样长。
#   · **旁白没有 beat**：三方各判 0~1 条，且与 paragraph 无法区分。旁白是叙述，
#     没有「对谁说重话」的情绪落点。
#
# 位置不是问题：18.34 实测逗号 218 处只有 4% <0.12s、句号 143 处只有 1%，
# 非标点 2149 处 98% 为 0 ⇒ 96% 的逗号都停，"该不该停"不存在。
MARKS = {
    "inner":  (0.35, 0.70),   # median 0.51 —— 前半不完整
    "bound":  (0.95, 1.35),   # median 1.135 —— 前半完整，后半是新成分
    "clause": (1.50, 2.00),   # median 1.695 —— 句子结束
}


def main():
    chunk = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    path = sys.argv[3] if len(sys.argv) > 3 else "G:/_setup/_pause_vote/p_lead_b%d.jsonl" % chunk

    ctx = [json.loads(l) for l in open(CTX, encoding="utf-8") if l.strip()]
    want = [r["bid"] for r in ctx[chunk * n:(chunk + 1) * n]]
    got = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    gb = [r["bid"] for r in got]

    print("应判 %d 条 / 实判 %d 条" % (len(want), len(gb)))
    miss = [b for b in want if b not in set(gb)]
    extra = [b for b in gb if b not in set(want)]
    dup = [b for b, c in collections.Counter(gb).items() if c > 1]
    if miss:
        print("✗ 漏 %d: %s" % (len(miss), miss[:10]))
    if extra:
        print("✗ 多 %d: %s" % (len(extra), extra[:10]))
    if dup:
        print("✗ 重复: %s" % dup[:10])
    order_ok = gb == want[:len(gb)]
    print("顺序一致:", order_ok)

    bad = []
    for r in got:
        lo, hi = MARKS.get(r.get("mark"), (None, None))
        if lo is None:
            bad.append((r["bid"], "mark 非法 " + str(r.get("mark"))))
        elif not (lo - 1e-9 <= float(r.get("dur", -1)) <= hi + 1e-9):
            bad.append((r["bid"], "dur %.2f 不在 %s 区间" % (float(r.get("dur", -1)), r.get("mark"))))
        if not (r.get("why") or "").strip():
            bad.append((r["bid"], "why 为空"))
    if bad:
        print("✗ 取值问题 %d:" % len(bad), bad[:8])
    if not (miss or extra or dup or bad) and order_ok:
        print("✓ 本批通过")
    print("mark 分布:", dict(collections.Counter(r["mark"] for r in got)))
    print("合计停顿 %.1fs" % sum(float(r["dur"]) for r in got))


if __name__ == "__main__":
    main()
