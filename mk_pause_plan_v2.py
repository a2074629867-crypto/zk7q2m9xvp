# -*- coding: utf-8 -*-
"""旁白停顿计划 v2 —— 三档（inner / bound / clause），优先用 LLM 标注。

为什么要有 v2：
  `_pause_plan.jsonl`（v1）是 2026-11-11 11:08 的**兜底表**，档位名和值来自
  `pause_tiers.json`（zero/marker/short 0.7/mid 1.16/dot_inner 0.85/? 0.24），
  判据是「左边几个词」这种长度启发式，**不是** NARR_STANDARD §5.2 的句法阶梯。
  实测 1085 处：无一处于三档值，clause（1.695）整档缺失；73 处句末全是 0.85/0.7。

v2 生成优先级（与 REQUIREMENTS 19/19b 一致）：
  1. LLM 标注（`_ann/out_full/narr/ds/`，716 句 / 1079 槽）→ tier 经 ann_spec 换成 kind+秒
  2. 标注与表对不上的 13 处 → 本脚本里的 REJUDGE / DROP 逐条定，带 why
  3. 不猜、不取平均：判不了就丢并记进台账

输出：`_pause_plan_v2.jsonl`（新增文件，不动 v1）+ `_pause_plan_v2_log.json`
"""
import json, glob, collections, sys
sys.path.insert(0, "G:/_setup")
import ann_spec

CTX = "G:/_setup/_pause_ctx.jsonl"
V1 = "G:/_setup/_pause_plan.jsonl"
ANN = "G:/_setup/_ann/out_full/narr/ds/batch_*.json"
OUT = "G:/_setup/_pause_plan_v2.jsonl"
LOG = "G:/_setup/_pause_plan_v2_log.json"
TRACK = "narr"

# 标注漏判、但阶梯能定的 7 处（逐条人判，why 照 §5.2 写）
REJUDGE = {
  "c1_0097#6": ("bound",  "右段 who attracts attention 是关系从句，修饰 a man → 阶梯 4"),
  "c1_0100#6": ("bound",  "右段 it would make up for a good deal 有主谓，新分句 → 阶梯 7"),
  "c1_0173#3": ("inner",  "右段 Lutestring Moths 是列举的末项，无谓语 → 阶梯 5"),
  "c1_0186#3": ("bound",  "右段 the ink had faded… 有主谓，新分句 → 阶梯 7"),
  "c2_0420#3": ("inner",  "右段 a stranger in his son's room 是 intruder 的同位语 → 阶梯 5"),
  "c3_0554#1": ("bound",  "右段 all the individual branches were clearly outlined 有主谓（破折号后新分句） → 阶梯 7"),
  "c3_0761#3": ("inner",  "右段 nearer to him 是补充成分，删掉句子仍成立 → 阶梯 5"),
}

# 两表都判了、但根本不是边界：省略号被拆成多个点 / 截断句末的逗号
DROP = {
  "c2_0492#8":  "省略号尾部的第二个点，同一处边界重复计数",
  "c3_0729#7":  "句末省略号，条末停顿由拼接器给，不属条内",
  "c3_0729#8":  "句末省略号的第三个点，重复计数",
  "c3_0749#3":  "句末省略号，条末停顿由拼接器给",
  "c3_0899#3":  "句末省略号，条末停顿由拼接器给",
  "c3_0911#4":  "句末省略号，条末停顿由拼接器给",
  "c1_0128#4":  "截断句末尾的逗号（原文到此断条），不属条内",
  "c1_0144#5":  "截断句末尾的逗号，不属条内",
  "c1_0176#3":  "截断句末尾的逗号，不属条内",
  "c2_0208#4":  "截断句末尾的逗号，不属条内",
  "c2_0422#8":  "截断句末尾的逗号，不属条内",
  "c2_0476#2":  "截断句末尾的逗号，不属条内",
  "c3_0845#4":  "截断句末尾的逗号，不属条内",
}


def main():
    ctx = {}
    for l in open(CTX, encoding="utf-8"):
        r = json.loads(l); ctx[r["bid"]] = r
    v1 = [json.loads(l) for l in open(V1, encoding="utf-8") if l.strip()]
    ann = {}
    for f in sorted(glob.glob(ANN)):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            for p in it["pause"]:
                ann[p["bid"]] = p

    rows, dropped, unknown, src_c = [], [], [], collections.Counter()
    bids = sorted(set(r["bid"] for r in v1) | set(ann))
    for b in bids:
        if b in DROP:
            dropped.append({"bid": b, "reason": DROP[b]}); continue
        if b in REJUDGE:
            kind, why = REJUDGE[b]
            src = "llm_rejudged"
        elif b in ann and b in ctx:
            kind = ann_spec.kind_of_tier(TRACK, ann[b].get("tier"))
            why = ann[b].get("why", "")
            src = "llm"
            if kind is None:
                unknown.append({"bid": b, "tier": ann[b].get("tier")}); continue
        elif b in ann:
            unknown.append({"bid": b, "tier": ann[b].get("tier"), "why": "无 ctx（文本源没有这条）"}); continue
        else:
            unknown.append({"bid": b, "tier": v1_tier(v1, b), "why": "标注没覆盖，且未列入 REJUDGE"}); continue
        dur = ann_spec.sec_of_kind(TRACK, kind)
        assert dur is not None, (b, kind)
        c = ctx.get(b, {})
        rows.append({"bid": b, "sid": b.split("#")[0], "k": c.get("k"),
                     "punct": c.get("punct"), "kind": kind, "dur": dur,
                     "tier_from": ann.get(b, {}).get("tier"), "src": src, "why": why})
        src_c[src] += 1

    rows.sort(key=lambda r: (r["sid"], r["k"] or 0))
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def stat(rs, key):
        d = collections.Counter(r[key] for r in rs)
        return {k: (v, round(v * ann_spec.KIND_SEC[TRACK].get(k, 0), 2)) for k, v in d.items()}

    v1_dur = sum(r["dur"] for r in v1)
    v2_dur = sum(r["dur"] for r in rows)
    # 只看共同的 bid，比较同位置前/后 差值最大的
    v1map = {r["bid"]: r for r in v1}
    delta = sorted(((r["dur"] - v1map[r["bid"]]["dur"], r["bid"], v1map[r["bid"]]["tier"],
                     v1map[r["bid"]]["dur"], r["kind"], r["dur"])
                    for r in rows if r["bid"] in v1map), key=lambda x: -abs(x[0]))
    log = {
        "v1": {"slots": len(v1), "total_s": round(v1_dur, 2), "by_tier": stat(v1, "tier")},
        "v2": {"slots": len(rows), "total_s": round(v2_dur, 2), "by_kind": stat(rows, "kind"),
                "src": dict(src_c)},
        "dropped": dropped, "unknown": unknown,
        "delta_total_s": round(v2_dur - v1_dur, 2),
        "delta_top20": [{"bid": b, "v1": [t, d], "v2": [k, dd], "d": round(x, 3)}
                        for x, b, t, d, k, dd in delta[:20]],
        "sentences_with_plan": len({r["sid"] for r in rows}),
    }
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("v1 %d 处 / %.2fs  →  v2 %d 处 / %.2fs  (Δ %+.2fs)" %
          (len(v1), v1_dur, len(rows), v2_dur, v2_dur - v1_dur))
    print("v2 档位:", {k: (v[0], v[1]) for k, v in log["v2"]["by_kind"].items()})
    print("v2 来源:", dict(src_c), "| 丢弃 %d 处 | 待定 %d 处" % (len(dropped), len(unknown)))
    print("覆盖句子: %d" % log["sentences_with_plan"])
    print("变化最大的 8 处:")
    for x, b, t, d, k, dd in delta[:8]:
        print("   %-12s %-9s %.2f → %-6s %.3f  (%+.2fs)" % (b, t, d, k, dd, x))


def v1_tier(v1, b):
    for r in v1:
        if r["bid"] == b:
            return r["tier"]
    return None


if __name__ == "__main__":
    main()
