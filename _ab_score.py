# -*- coding: utf-8 -*-
"""读 _ab_votes.jsonl，把 10 票换算成「救回档 / 控制档 / 反向档」的命中数，并给出判据去向。

用法：python _ab_score.py
"""
import json
import sys

BAND = {
    "c2_0191": ("救回", 0.00, 0.57),
    "c1_0048": ("救回", 0.00, 0.52),
    "c1_0061": ("救回", 0.00, 0.64),
    "c2_0495": ("救回", 0.00, 0.89),
    "c1_0024": ("救回", 0.06, 0.73),
    "c1_0012": ("控制", 0.40, 0.38),
    "c3_0762": ("控制", 0.41, 0.41),
    "c2_0196": ("反向", 0.60, 0.25),
    "c2_0514": ("反向", 0.61, 0.31),
    "c3_0544": ("反向", 0.61, 0.00),
}


def load_last():
    rec = None
    with open("G:/_setup/_ab_votes.jsonl", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            try:
                body = json.loads(r["body"])
            except Exception:
                continue
            if isinstance(body.get("votes"), list) and len(body["votes"]) >= 10:
                rec = body
    return rec


def main():
    rec = load_last()
    if not rec:
        print("还没收到完整投票（需要 10 条）。")
        sys.exit(1)

    rows = []
    for v in rec["votes"]:
        sid = v["id"]
        if sid not in BAND:
            continue
        band, co, cn = BAND[sid]
        a_is_new = v.get("A") == "new"
        vote = v.get("vote")
        if vote == "A":
            win = "new" if a_is_new else "old"
        elif vote == "B":
            win = "old" if a_is_new else "new"
        else:
            win = vote
        rows.append((band, sid, co, cn, win, v.get("word") or ""))

    print(f"{'档':<4}{'句':<10}{'old':>6}{'new':>7}{'Δ':>7}  {'你选':<10} 词")
    for band, sid, co, cn, win, word in rows:
        tag = {"new": "三档版", "old": "验收版", "both_bad": "两版都糊", "same": "听不出"}.get(win, str(win))
        print(f"{band:<4}{sid:<10}{co:>6.2f}{cn:>7.2f}{cn-co:>+7.2f}  {tag:<10} {word}")

    rescue = [r for r in rows if r[0] == "救回"]
    ctrl = [r for r in rows if r[0] == "控制"]
    rev = [r for r in rows if r[0] == "反向"]

    r_win = sum(1 for r in rescue if r[4] == "new")
    c_same = sum(1 for r in ctrl if r[4] in ("same", "both_bad"))
    v_win = sum(1 for r in rev if r[4] == "old")

    print(f"\n救回档 三档版胜 {r_win}/{len(rescue)}")
    print(f"控制档 听不出   {c_same}/{len(ctrl)}")
    print(f"反向档 验收版胜 {v_win}/{len(rev)}")

    print("\n判据去向：")
    if r_win >= 4 and v_win >= 2:
        print("  ★ 走向 a：3.4 双向成立（正向救回 + 反向回退都被你听出来）")
        print("    ⇒ 阈值 0.20 定死；113 句（cover<0.10）进返工队列，分批换 seed 重生成")
    elif r_win >= 4 and v_win <= 1:
        print("  ★ 走向 b：只有救回档成立 ⇒ 3.4 只用于「救回」，反向档另查（先看是否落在功能词上）")
    elif r_win <= 2:
        print("  ★ 走向 c：救回档都没命中 ⇒ 3.4 撤回，退回 3.1 + unstable 单轨")
    else:
        print("  ★ 走向 d：混合，按句子逐条看（下表已列），先信你的耳朵再改阈值")
        # 逐条判读
        for band, sid, co, cn, win, word in rows:
            if band == "救回" and win != "new":
                print(f"    · {sid} 救回档没听出新版更好（Δ{cn-co:+.2f}）⇒ 它不该在返工队列里")


if __name__ == "__main__":
    main()
