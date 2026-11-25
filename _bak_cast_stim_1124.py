# -*- coding: utf-8 -*-
"""强度感知选角（stim-aware casting）：把 intensity 真正接进生成链。

为什么需要它
------------
`_stim_report.md` 第三节的硬证据：21 / 21 个 (角色,情绪) 组的 I1/I2/I3
**共用同一个参考切片**（如 Thomas_激动反抗 三级全部用 `Thomas_loud_1`）。
生成是零误声克隆，情绪与强度完全由被克隆的切片决定，文本侧不传强度标签。
⇒ 强度在输入端就不存在，拿同一档重跑多少次都不会出现梯度。

修法
----
同一情绪格里通常有 3–4 条真人切片，它们的发声努力度**实测不同**
（例：Charles soft 三条 effort −1.51 / −1.25 / −0.57，跰度 0.94）。
按实测 effort 排序，I1 取最低、I3 取最高、I2 取中间，强度就有了真实差异。

两条硬约束
----------
1. **不跨情绪格**。强度不能靠借相邻情绪实现（那会把「委屈」变成「求悦」），
   只在已确定的那个格里调。格内切片不够就**如实报不够**，不拿别的格填。
2. **不按切片序号猜强度**。`_1/_2/_3` 只是库里的顺序，与强弱无关；
   必须按 `_stim_ref.json` 的实测 effort 排（
   例：Thomas loud 四条 effort 为 +0.50/+0.54/+0.67/+1.08）。

不够怎么办
----------
每个格算「I1 → I3 的 effort 跰度」，对照闸门要求（min 0.30 z）：
  · ≥0.30 ⇒ 可支撑三档
  · <0.30 ⇒ 该格切片太同质，换切片也抳不开 → 需补录同角色同情绪的高/低强度参考
需求侧也一并算：某格没有 I3 台词就不报缺口，不虚报工作量。

输出
----
`_castle_en_ch123_plan_v3.jsonl`  新计划（voice 换成强度对应切片）
`_stim_cast.json`               每个格的选角表（含 effort / 跰度 / 结论）
`_stim_cast.md`                 人读报告
`_stim_pilot.json`              可直接喂 `regen_r3.py` 的试跑清单

用法
----
    G:/Python310/python.exe cast_stim.py            # 建表 + 写 plan_v3
    G:/Python310/python.exe cast_stim.py --pilot 6  # 另出 6 条试跑清单
"""
import os
import sys
import json
import math
import argparse
import collections
import statistics as st

LIB = "G:/_setup/_emo_refs_all.json"
REFF = "G:/_setup/_stim_ref.json"
PLAN = "G:/_setup/_castle_en_ch123_plan_v2.jsonl"
OUT_PLAN = "G:/_setup/_castle_en_ch123_plan_v3.jsonl"
OUT_CAST = "G:/_setup/_stim_cast.json"
OUT_MD = "G:/_setup/_stim_cast.md"
OUT_PILOT = "G:/_setup/_stim_pilot.json"

GAP_MIN = 0.30          # 与 stim_tier 的档间最小极差一致

# (角色, 中文情绪) -> 英文格。与 rebuild_plan_v2.py 的 V 表一致，
# 但拆成「主格 / 退路格」两层，退路格要标出来（库缺档，不是我们选错）。
CELL = {
    "Charles": {"平静": ("neutral", False), "兴奋": ("excited", False),
                "激动反抗": ("angry", False), "委屈": ("soft", False),
                "紧张": ("soft", True), "警惕": ("soft", True)},
    "Thomas": {"平静": ("calm", False), "兴奋": ("loud", True),
               "激动反抗": ("loud", False), "委屈": ("begging", False),
               "紧张": ("calm", True), "警惕": ("scold", False)},
    "Joseph": {"平静": ("normal", False), "兴奋": ("excited", False),
               "激动反抗": ("defiant", False), "委屈": ("wronged", False),
               "紧张": ("nervous", False), "警惕": ("wary", False)},
    "Helena": {"平静": ("wary", True), "兴奋": ("excited", False),
               "激动反抗": ("defiant", False), "委屈": ("wronged", False),
               "紧张": ("nervous", False), "警惕": ("wary", False)},
}


def params(sub, k):
    v = [r[k] for r in sub if r.get(k) is not None]
    if len(v) < 3:
        return (st.median(v) if v else None), 1.0
    return st.median(v), (st.pstdev(v) or 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0, help="另出 N 条试跑清单")
    a = ap.parse_args()

    lib = json.load(open(LIB, encoding="utf-8"))
    refs = json.load(open(REFF, encoding="utf-8"))
    plan = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]

    # 角色内定标（与 stim_tier 一致）：用该角色全部真人切片
    per = {w: {k: params([r for r in refs if r["who"] == w], k)
               for k in ("alpha", "f0_med", "hnr")}
           for w in set(r["who"] for r in refs)}

    def effort(r):
        P = per.get(r["who"]) or {}
        z, n = 0.0, 0
        for k, sign in (("alpha", -1), ("f0_med", 1), ("hnr", -1)):
            v = r.get(k)
            if v and P.get(k, (None,))[0] is not None:
                z += sign * (v - P[k][0]) / P[k][1]
                n += 1
        return z / n if n else None

    # 基准名 -> effort（切片 path 的 basename 在 refs 与库里能对上）
    by_base = {}
    for r in refs:
        e = effort(r)
        if e is not None:
            by_base[(r["who"], r["emo"], r["ref"])] = e

    # 每个格的候选切片（voice 名靠 lib 里的顺序定，1-based）
    pool = {}
    for who, m in CELL.items():
        for emo, (tier, fb) in m.items():
            items = (lib.get(who) or {}).get(tier) or []
            cand = []
            for i, it in enumerate(items):
                p = it.get("path") if isinstance(it, dict) else it
                base = os.path.basename(p or "")
                e = by_base.get((who, tier, base))
                cand.append(dict(voice="%s_%s_%d" % (who, tier, i + 1), base=base,
                                 effort=None if e is None else round(e, 3)))
            cand = [c for c in cand if c["effort"] is not None]
            cand.sort(key=lambda c: c["effort"])
            pool[(who, emo)] = dict(tier=tier, fallback=fb, cand=cand)

    # 需求侧：每个格各档多少条台词
    need = collections.defaultdict(collections.Counter)
    for r in plan:
        if r.get("speaker") == "narrator" or not r.get("emo"):
            continue
        who = {"Edmund": "Thomas", "Other": "Helena"}.get(r["speaker"], r["speaker"])
        if (who, r["emo"]) in pool:
            need[(who, r["emo"])][int(r.get("emo_intensity") or 0)] += 1

    # 三档选切片：按 effort 升序取 最低 / 中间 / 最高
    cast = {}
    for key, P in pool.items():
        cand = P["cand"]
        n = len(cand)
        chosen = {}
        if n == 0:
            goto = "空"
        else:
            idxs = {1: 0, 2: int(round((n - 1) / 2.0)), 3: n - 1}
            for lv, j in idxs.items():
                chosen[lv] = cand[j]
            goto = "可支撑" if (cand[-1]["effort"] - cand[0]["effort"]) >= GAP_MIN else "切片太同质"
            if n < 3:
                goto = "切片不足 n=%d" % n
        needn = need.get(key, collections.Counter())
        cast["%s|%s" % key] = dict(
            who=key[0], emo=key[1], tier=P["tier"], fallback=P["fallback"], n=n,
            cand=cand, pick=chosen, verdict=goto,
            gap=round(cand[-1]["effort"] - cand[0]["effort"], 3) if n >= 2 else None,
            need={str(k): v for k, v in sorted(needn.items())})

    # 写 plan v3
    out = []
    changed = 0
    thin = collections.Counter()
    for r in plan:
        r = dict(r)
        if r.get("speaker") != "narrator" and r.get("emo"):
            who = {"Edmund": "Thomas", "Other": "Helena"}.get(r["speaker"], r["speaker"])
            c = cast.get("%s|%s" % (who, r["emo"]))
            lv = int(r.get("emo_intensity") or 2)
            if c and c["pick"].get(lv):
                new = c["pick"][lv]["voice"]
                if new != r.get("voice"):
                    changed += 1
                r["voice"] = new
                r["voice_src"] = "cast_stim_v3"
                r["voice_lv_effort"] = c["pick"][lv]["effort"]
                if c["pick"][lv]["effort"] == c["pick"].get(1, {}).get("effort") and lv == 3:
                    thin[(who, r["emo"])] += 1
        out.append(r)

    with open(OUT_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(cast, open(OUT_CAST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 报告
    L = []
    A = L.append
    A("# 强度感知选角表（v3）\n\n")
    A("把 `intensity` 从「写进计划但没人读」变成「选哪个参考切片」。\n")
    A("排序依据：该切片实测 effort（−z(alpha)+z(f0中位)−z(HNR)，角色内定标）；\n")
    A("**不按 `_1/_2/_3` 序号猜**，序号只是库里的顺序。\n\n")
    A("| 角色 | 情绪 | 格 | 需求 n(I1/I2/I3) | 切片数 | I1 → I3 选中 | 跃度 | 结论 |\n")
    A("|---|---|---|---|---|---|---|---|\n")
    order = sorted(cast.values(), key=lambda c: -sum(c["need"].values()))
    for c in order:
        if sum(c["need"].values()) == 0:
            continue
        p = c["pick"]
        sel = " / ".join("%s %+0.2f" % (p[k]["voice"].split("_", 1)[1], p[k]["effort"])
                        for k in (1, 2, 3) if k in p)
        nd = "/".join(str(c["need"].get(str(k), 0)) for k in (1, 2, 3))
        mark = c["verdict"]
        if c["fallback"]:
            mark += "（库缺档，用退路格）"
        A("| %s | %s | %s | %s | %d | %s | %s | %s |\n" % (
            c["who"], c["emo"], c["tier"], nd, c["n"], sel,
            "%+0.2f" % c["gap"] if c["gap"] is not None else "-", mark))

    bad = [c for c in cast.values() if sum(c["need"].values()) > 0 and c["verdict"] != "可支撑"]
    A("\n## 缺口（需补录同角色同情绪的高低强度参考）\n\n")
    if not bad:
        A("无。所有有需求的格都能在格内抳开 ≥%.2f 的 effort 跃度。\n" % GAP_MIN)
    else:
        for c in sorted(bad, key=lambda c: -sum(c["need"].values())):
            A("- **%s / %s**（%s，n=%d，跃度 %s，需求 %s）：%s\n" % (
                c["who"], c["emo"], c["tier"], c["n"],
                "%+0.2f" % c["gap"] if c["gap"] is not None else "-",
                sum(c["need"].values()), c["verdict"]))

    A("\n## 不变的部分\n\n")
    A("- 情绪格本身没改：仍是 `rebuild_plan_v2.py` 定的格，跨格借档的情况照样标 `emo_unsupported`。\n")
    A("- 不改语速/降速/电压：本步只换参考切片，`rate` 与后续归一化不变。\n")
    A("- 共用同一句台词文本，换的只是音色参考，所以声纹一致性仍需 `_segcheck_dlg.py` 重新验。\n")
    open(OUT_MD, "w", encoding="utf-8").write("".join(L))

    print("plan %d 行 → %s（voice 变动 %d 行）" % (len(out), OUT_PLAN, changed))
    print("选角表 → %s / %s" % (OUT_CAST, OUT_MD))
    print("有需求且支撑不了三档的格：%d" % len(bad))
    for c in sorted(bad, key=lambda c: -sum(c["need"].values()))[:8]:
        print("   %-8s %-6s %-8s n=%d 跃度 %s %s" % (
            c["who"], c["emo"], c["tier"], c["n"],
            "%+0.2f" % c["gap"] if c["gap"] is not None else "-", c["verdict"]))

    if a.pilot:
        # 优先挑「同一格三档都有」的格，保证能看出梯度
        picks = []
        for c in order:
            if all(c["need"].get(str(k), 0) >= 1 for k in (1, 2, 3)) and c["verdict"] == "可支撑":
                for lv in (1, 2, 3):
                    pid = next((r["id"] for r in out
                                if r.get("speaker") != "narrator"
                                and {"Edmund": "Thomas", "Other": "Helena"}.get(r["speaker"], r["speaker"]) == c["who"]
                                and r.get("emo") == c["emo"]
                                and int(r.get("emo_intensity") or 0) == lv
                                and r.get("voice") == c["pick"][lv]["voice"]), None)
                    if pid:
                        picks.append({"id": pid, "role": c["who"], "emo": c["emo"],
                                      "voice": c["pick"][lv]["voice"], "lv": lv})
                if len(picks) >= a.pilot:
                    break
        picks = picks[:a.pilot]
        json.dump(picks, open(OUT_PILOT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("试跑清单 %d 条 → %s" % (len(picks), OUT_PILOT))
        for p in picks:
            print("   %-10s %-6s L%d %s" % (p["id"], p["emo"], p["lv"], p["voice"]))


if __name__ == "__main__":
    main()
