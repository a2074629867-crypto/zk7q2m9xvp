# -*- coding: utf-8 -*-
"""最终交付报告：把七闸（v41）+ 短句专用验收合并成一份口径清楚的清单。

为什么合并：七闸对 <1.6s 的短句给 MANUAL（声纹/情绪物理不可测），
短句闸用「内容 + 电平 + 静音 + 自然度」另判。两张表必须并成一张，
否则交付时说不清「239 条里到底多少能用」。

用法：G:/Python310/python.exe _final_report.py [--gate _gate_dlg_v41.json]
"""
import argparse
import collections
import io
import json
import os
import sys

S = "G:/_setup"
sys.path.insert(0, S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=os.path.join(S, "_gate_dlg_v41.json"))
    ap.add_argument("--short", default=os.path.join(S, "_short_gate.json"))
    ap.add_argument("--out", default=os.path.join(S, "_dlg_final_report.md"))
    ap.add_argument("--json", default=os.path.join(S, "_dlg_final.json"))
    a = ap.parse_args()

    g = json.load(io.open(a.gate, encoding="utf-8"))
    sg = {x["id"]: x for x in json.load(io.open(a.short, encoding="utf-8"))}
    plan = {}
    for l in io.open(os.path.join(S, "_dlg_plan_v2_paused.jsonl"), encoding="utf-8"):
        if l.strip():
            x = json.loads(l)
            plan[x["id"]] = x

    rows = []
    cnt = collections.Counter()
    for x in g:
        sid = os.path.basename(x["wav"])[:-4]
        st = x["verdict"]
        if sid in sg:
            s = sg[sid]
            if s["verdict"] == "S_PASS":
                cls, why = "A_S", "短句判据通过（内容/电平/静音/自然度）"
            else:
                cls, why = "D", "短句判据未过：" + ",".join(s["reasons"])
        elif st == "PASS":
            cls, why = "A", "七闸全过"
        elif st == "REGEN":
            cls, why = "C", "生成层推不动（" + ",".join(r["code"] for r in (x.get("reasons") or [])) + "）"
        else:
            cls, why = "E", "情绪边缘/生成层不可达（" + ",".join(r["code"] for r in (x.get("reasons") or [])) + ")"
        cnt[cls] += 1
        rows.append(dict(id=sid, cls=cls, why=why, who=x.get("who"), emo=x.get("emo"),
                         dur=(x.get("tech") or {}).get("dur"),
                         emo_val=(x.get("emo_res") or {}).get("value"),
                         text=(plan.get(sid) or {}).get("text", "")[:70]))

    n = len(rows)
    ok = cnt["A"] + cnt["A_S"]
    lines = ["# 对白交付最终报告（七闸 + 短句验收合并）", "",
             "数据源：`%s`（239 条）+ `%s`" % (os.path.basename(a.gate), os.path.basename(a.short)), "",
             "## 一、最终分档", "",
             "| 类 | 含义 | 条数 | 占比 |", "|---|---|---|---|",
             "| A | 七闸全过（声学/声纹/情绪/句内/档内/自然度/音色） | %d | %.1f%% |" % (cnt["A"], 100.0 * cnt["A"] / n),
             "| A_S | 短句判据通过（声纹/情绪不可测，改用 内容/电平/静音/自然度） | %d | %.1f%% |" % (cnt["A_S"], 100.0 * cnt["A_S"] / n),
             "| E | 情绪边缘 / 撞素材数学上限（可听，需人耳） | %d | %.1f%% |" % (cnt["E"], 100.0 * cnt["E"] / n),
             "| C | 生成层推不动（情绪贴地/素材上限，需人耳） | %d | %.1f%% |" % (cnt["C"], 100.0 * cnt["C"] / n),
             "| D | 短句未过内容判据（需重做/人耳） | %d | %.1f%% |" % (cnt["D"], 100.0 * cnt["D"] / n),
             "", "**验收通过：%d / %d = %.1f%%**" % (ok, n, 100.0 * ok / n),
             "**可听（通过 + 情绪边缘）：%d / %d = %.1f%%**" % (ok + cnt["E"], n, 100.0 * (ok + cnt["E"]) / n),
             ""]

    drows = [r for r in rows if r["cls"] == "D"]
    if drows:
        lines += ["## 二、短句未过明细（全部为极短句）", "",
                  "| id | 角色 | 时长 | 原文 | 原因 |", "|---|---|---|---|---|"]
        for r in drows:
            lines.append("| %s | %s | %.2fs | %s | %s |" % (r["id"], r["who"], r["dur"] or 0,
                                                          r["text"], r["why"]))
        lines.append("")

    crows = [r for r in rows if r["cls"] == "C"]
    if crows:
        lines += ["## 三、生成层推不动（C）", "", "| id | 角色 | 情绪 | 时长 | 原因 |", "|---|---|---|---|---|"]
        for r in crows:
            lines.append("| %s | %s | %s | %.2fs | %s |" % (r["id"], r["who"], r["emo"], r["dur"] or 0, r["why"]))
        lines.append("")

    erows = [r for r in rows if r["cls"] == "E"]
    lines += ["## 四、情绪边缘（E，%d 条）" % len(erows), "",
              "| id | 角色 | 情绪 | 值 | 原因 |", "|---|---|---|---|---|"]
    for r in erows:
        v = r["emo_val"]
        lines.append("| %s | %s | %s | %s | %s |" % (r["id"], r["who"], r["emo"],
                                                    "—" if v is None else "%.3f" % v, r["why"]))
    lines.append("")

    io.open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(rows, io.open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(dict(cnt), "通过 %d/%d = %.1f%%" % (ok, n, 100.0 * ok / n))
    print("写出", a.out, a.json)


if __name__ == "__main__":
    main()
