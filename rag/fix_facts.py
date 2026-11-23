# -*- coding: utf-8 -*-
"""修正 facts.jsonl 里的「状态标签与实际含义不符」问题。

为什么必须做（用户 2026-11-11 指出：「RAG 这里固定的数据不一定是正确的，
时间顺序不同的、已经踩过的经验可能都混在一起，结论可能不一致」）：

  facts.jsonl 是 append-only 的账本，每条结论的 body 里既有**原结论**又有
  **后来的【作废批注】**。检索时按 chunk 切，很可能只命中前半段（错数字），
  漏掉后半段（"2026-11-08 作废"）。这比没有账本更危险。

  实测三类问题：
    A. 6 条 status="作废-测量bug" —— 其中 4 条是「方向成立、数字算错」（结论仍有效），
       2 条（124/125）是**结论真反转**。同一个 status 表示两种含义，不可读。
    B. [109][110] topic 带「【已作废·见新定稿】」但 status 仍是「定稿」。
    C. [1] 声纹阈值写「段间 <0.55 判异常」，[80] 又写「旧声纹红线 0.55 已作废」，
       两处字面冲突（实际是不同模型口径，[80] 说的是 CAM++ 换模型后要重估）。

本脚本只改 status 字段（加 ⛔ 前缀让检索输出一眼可见），**不动 conclusion 正文**，
并打印需要人工裁决的清单。原文件先备份。

用法：
  python fix_facts.py            # 只报告，不写
  python fix_facts.py --apply
"""
import argparse
import json
import shutil
import time

FACTS = "G:/_setup/rag/facts.jsonl"

# id -> (新 status, 一句话说明)。按 topic 匹配，避免 id 漂移。
RULES = [
    # A. 作废-测量bug：数字错但方向有效 → 标「⛔数字作废」而不是全盘否定
    ("对白闸门 soft 档角色/情绪分离", "⛔数字作废·方向有效",
     "soft 档只做情绪参考不参与角色归属 = dialog_gate 默认口径，仍然有效；错的只是 29→33 那组数字"),
    ("role_gap 是相对值，必须配绝对下限", "⛔数字作废·保护保留",
     "z_target<=0 判 MANUAL 作为兜底保留，59 条上不触发"),
    ("生成到闸门回路已闭环，短句必崩可自动检出", "⛔数字作废·见新定稿",
     "z 算错，正确是 TQ1_s7301 情绪 0.793 / gap +0.45 / PASS"),
    ("两视角冲突规则在 TTS 产物上命中率异常高", "⛔收益为0·已默认关",
     "4/4 命中是真的，但「代价」被放大；修好后收益为 0，规则已关"),
    # A'. 结论真反转：这两条必须全盘标记
    ("自动切的素材全量并库是陷阱", "⛔结论反转·勿引用",
     "全量并库实测最好（42 PASS/100%/91.5%）；原结论是 z 数组 dict key 覆盖导致算错"),
    ("并库要按角色配平才对判定有正收益", "⛔结论反转·勿引用",
     "配平非必要，全量并库 42 PASS 优于只补 Charles 的 37"),
    # B. topic 已写「已作废」但 status 没跟上
    ("【已作废·见新定稿】Cam++ 认人二分类在本片不可用（附 LOO 实测）", "⛔已撤回",
     "2026-11-07 23:25 撤回：错把 Cam++ 判为认人不可用，且用了用户禁止的 F0 做校验"),
    ("【已作废·见新定稿】二分类认人正解是语义角色+F0校验，标签只进中文翻译标注", "⛔已撤回",
     "同上，撤回"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(FACTS, encoding="utf-8") if l.strip()]
    by_topic = {r.get("topic", ""): i for i, r in enumerate(rows)}

    plan = []
    for topic, new_status, why in RULES:
        i = by_topic.get(topic)
        if i is None:
            print("✗ 找不到 topic：%s" % topic[:40])
            continue
        old = rows[i].get("status", "")
        if old == new_status:
            print("· 已是目标状态：%s" % topic[:36])
            continue
        plan.append((i, topic, old, new_status, why))

    print()
    print("=== 待改 %d 条 ===" % len(plan))
    for i, topic, old, new, why in plan:
        print("[%3d] %s" % (i, topic[:44]))
        print("      %s  →  %s" % (old, new))
        print("      理由：%s" % why)

    print()
    print("=== 状态分布（改前） ===")
    import collections
    print(dict(collections.Counter(r.get("status", "") for r in rows)))

    if not a.apply:
        print()
        print("（未写盘。加 --apply 执行）")
        return

    bak = FACTS + ".bak." + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(FACTS, bak)
    print("已备份 →", bak)

    for i, topic, old, new, why in plan:
        rows[i]["status"] = new

    with open(FACTS, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("已写回 %d 条" % len(rows))
    print("=== 状态分布（改后） ===")
    print(dict(collections.Counter(r.get("status", "") for r in rows)))
    print()
    print("⚠ 改完必须重新 index，否则检索仍用旧向量：")
    print("   cd G:/_setup/rag && G:/Python310/python.exe rag.py index")


if __name__ == "__main__":
    main()
