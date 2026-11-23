# -*- coding: utf-8 -*-
"""旁白停顿计划（两档来源，可混合）。

为什么要有两档：
  REQUIREMENTS 19-0 要求「停顿由 LLM 逐处判定，不给统计常数」；
  19b 明确写了「没有 LLM 判定时才用标点档位」作为**兜底**。
  2026-11-11 的 LLM 标注员两轮都撞 503 限流（per-model cooldown），
  所以先按兜底档位生成可跑的计划，标 `src="tier"`；
  LLM 标注到位后同 bid 覆盖，标 `src="llm"`。`pause_plan` 的覆盖优先级 llm > tier。

档位值取自 pause_tiers.json（逗号中位 1.16 / p75 1.53 是实测，其余是先验）。
句内句号用 dot_inner=0.85（1.56 是条间值，条内直接用会膨胀 78–90%）。
"""
import argparse
import json

CTX = "G:/_setup/_pause_ctx.jsonl"
TIERS = "G:/_setup/pause_tiers.json"
OUT = "G:/_setup/_pause_plan.jsonl"

MARKERS = {"well", "oh", "ah", "anyway", "now", "then", "so", "yes", "no",
           "look", "come", "why", "here", "there", "nothing", "something"}
# 语法性逗号：这些位置朗读基本不停（REQUIREMENTS 19: `All he looks like, is one of...` 判 0）
GLUE_PREV = {"like", "as", "than", "that", "is", "was", "which", "who", "whom"}


def tier_for(punct, left, right):
    lw = left.split()
    rw = right.split()
    if punct in (";", ":", "–"):
        return "mid"
    if punct == "?":
        return "?"          # 0.24s，n=1 脏样本，用户要求保留
    if punct == "!":
        return "mid"
    if punct == ".":
        # 句内句号：后面接 and/but/so/then 且语义连续 → short；否则 dot_inner
        if rw and rw[0].lower().strip(",.") in ("and", "but", "so", "then", "or"):
            return "short"
        return "dot_inner"
    # 逗号
    if lw and lw[-1].lower() in GLUE_PREV:
        return "zero"
    if len(lw) <= 2 and lw and lw[-1].lower() in MARKERS:
        return "marker"
    if len(lw) <= 3 or len(rw) <= 2:
        return "short"
    if len(lw) >= 9:
        return "long"
    return "mid"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--wpm", type=float, default=170.0,
                    help="本书旁白实测语速（narr_gate_phys 实测 p50=170wpm）")
    ap.add_argument("--ref-wpm", type=float, default=97.0,
                    help="pause_tiers 的标定语速（马修母带 97wpm 慢读）")
    ap.add_argument("--scale", action="store_true",
                    help="按 wpm 比例缩放档位（★默认关。2026-11-11 撤回：停顿不随 wpm 线性缩放）")
    ap.add_argument("--no-scale", action="store_true", help="(旧参数，保留兼容，等价于默认行为)")
    a = ap.parse_args()
    tiers = json.load(open(TIERS, encoding="utf-8"))

    # ★★★ 2026-11-11 撤回缩放。三个理由：
    #   1. wpm 只算**语音段**速度（间隔已剔除），停顿时长是独立实测量，不随 wpm 线性缩放。
    #   2. pause_tiers 的 1.16/1.53 来自**旁白母带** wonder_train.wav（逗号 n=220 median 1.16
    #      / 句号 n=142 median 1.56），本来就是旁白的正确值，不是"别人的值"。
    #   3. 需求 19-0 那句「马修 1.16 拿给**情绪化对白**用会长出 2~3 倍」的主语是对白，
    #      被误读成「旁白要缩小」⇒ 产生了 ×0.57。
    #   代价：_pause_plan.jsonl 曾少插 481s（应 1120.2s，实际 638.5s），全库停顿只有标准 57%。
    #   见 DECISIONS.md「把 1.16/1.53 当成全局不能用的错值」。
    #   日志 2026-10-30 另有实测结论「比值不可跨体裁迁移」，同一件事。
    scale = 1.0
    if a.scale:
        scale = max(0.50, min(1.00, a.ref_wpm / a.wpm))

    rows = [json.loads(l) for l in open(CTX, encoding="utf-8") if l.strip()]
    out = []
    for r in rows:
        t = tier_for(r["punct"], r["left"], r["right"])
        base = tiers.get(t, 0.7)
        out.append({
            "bid": r["bid"], "sid": r["sid"], "punct": r["punct"],
            "tier": t, "dur": round(base * scale, 2), "src": "tier",
        })
    with open(a.out, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    import collections
    print("停顿计划 %d 条 -> %s（语速换算 %.0f/%.0f = ×%.2f）"
          % (len(out), a.out, a.ref_wpm, a.wpm, scale))
    print("档位:", dict(collections.Counter(o["tier"] for o in out)))
    tot = sum(o["dur"] for o in out)
    print("合计停顿 %.1fs（不含条间）" % tot)
    print("非零停:", sum(1 for o in out if o["dur"] > 0),
          "  零停:", sum(1 for o in out if o["dur"] == 0))


if __name__ == "__main__":
    main()
