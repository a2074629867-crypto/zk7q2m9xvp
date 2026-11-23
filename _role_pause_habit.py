# -*- coding: utf-8 -*-
"""_role_pause_habit.py —— 实测每个角色的「停顿习惯」

用户 2026-11-14 23:2x：
  「还得根据人物性格，有些人物停顿就是短一点，有些人物就是长一点，
   甚至有些人物不需要停顿，有些人物就要停顿，这是我们需要划清界限的。」

不能凭感觉写「Thomas 说话急」这种描述进 prompt。直接从**已交付的 239 条音频**
里测：每条音频内部的失声段（voiced 窗占比 <0.20 的连续窗）就是实际停顿。
窗 hop = 0.25s，所以「连续 n 个失声窗」≈ n × 0.25s。

输出 `_role_pause_habit.json`：
  {role: {n, pauses, p25, med, p75, p90, zero_rate, note}}
  zero_rate = 该角色「句内本该有标点却完全不停」的比例（要跟 _punct_expr 对齐）

用法：G:/Python310/python.exe _role_pause_habit.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
DRIFT = "G:/_setup/_drift_cache.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
PUNCT = "G:/_setup/_punct_expr.json"
OUT = "G:/_setup/_role_pause_habit.json"

HOP = 0.25          # mt_seg_drift 窗 hop
SIL_VOICED = 0.20   # voiced 低于此值算失声窗
MIN_GAP_WIN = 2     # 连续 >=2 个失声窗才算「停顿」（1 个窗 0.25s 多是辅音闭塞）


def main():
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        r = json.loads(l)
        plan[r["id"]] = r
    drift = json.load(open(DRIFT, encoding="utf-8"))
    punct = json.load(open(PUNCT, encoding="utf-8")) if os.path.exists(PUNCT) else {}

    by_role = {}
    detail = []
    for x in drift:
        sid = os.path.splitext(os.path.basename(str(x.get("file", "")).replace("\\", "/")))[0]
        if sid not in plan:
            continue
        ws = x.get("windows") or []
        if len(ws) < 4:
            continue
        voiced = [float(w.get("voiced") or 0) for w in ws]
        # 找连续失声段
        gaps = []
        run = 0
        for v in voiced + [1.0]:      # 哨兵，收尾时结算
            if v < SIL_VOICED:
                run += 1
            else:
                if run >= MIN_GAP_WIN:
                    # 掐掉首尾各半个窗（起音/收尾的软过渡）
                    gaps.append(round(max(0.0, (run - 1) * HOP), 2))
                run = 0
        who = plan[sid]["who"]
        by_role.setdefault(who, []).append(dict(sid=sid, dur=x.get("dur"), gaps=gaps,
                                                n_win=len(ws)))
        detail.append(dict(sid=sid, who=who, dur=x.get("dur"), gaps=gaps))

    # 句内标点槽位 → 该条「实际给了停顿吗」
    slot_stat = {}
    for sid, items in punct.items():
        if sid not in plan:
            continue
        n_slot = len(items)
        n_zero = sum(1 for it in items if it.get("status") == "none")
        slot_stat[sid] = dict(n=n_slot, zero=n_zero)

    out = {}
    print("%-9s %4s %6s %8s %8s %8s %8s %8s" %
          ("角色", "条数", "停顿数", "p25", "中位", "p75", "p90", "零停率"))
    for who in sorted(by_role):
        rows = by_role[who]
        g = [v for r in rows for v in r["gaps"]]
        s = [slot_stat[r["sid"]] for r in rows if r["sid"] in slot_stat]
        n_slot = sum(x["n"] for x in s)
        n_zero = sum(x["zero"] for x in s)
        rec = dict(n_utt=len(rows), n_pause=len(g),
                   p25=None, med=None, p75=None, p90=None,
                   zero_rate=(round(n_zero / n_slot, 3) if n_slot else None),
                   n_slot=n_slot, n_zero=n_zero)
        if g:
            gs = sorted(g)
            rec.update(p25=round(float(np.percentile(gs, 25)), 2),
                       med=round(float(np.percentile(gs, 50)), 2),
                       p75=round(float(np.percentile(gs, 75)), 2),
                       p90=round(float(np.percentile(gs, 90)), 2))
        out[who] = rec
        print("%-9s %4d %6d %8s %8s %8s %8s %8s" % (
            who, rec["n_utt"], rec["n_pause"], rec["p25"], rec["med"],
            rec["p75"], rec["p90"], rec["zero_rate"]))

    # 定性标签（给 prompt 用）
    print()
    print("=== 性格倾向（按实测定，不靠推断）===")
    for who, r in sorted(out.items(), key=lambda kv: (kv[1]["med"] or 0)):
        if r["med"] is None:
            lab = "样本不足"
        elif r["med"] <= 0.40:
            lab = "话急：停顿偏短"
        elif r["med"] <= 0.75:
            lab = "中等"
        else:
            lab = "话慢：停顿偏长"
        zr = r["zero_rate"]
        if zr is None:
            zlab = ""
        elif zr >= 0.45:
            zlab = "；常连读不停（零停率 %.0f%%）" % (100 * zr)
        elif zr <= 0.15:
            zlab = "；几乎处处停（零停率 %.0f%%）" % (100 * zr)
        else:
            zlab = "；零停率 %.0f%%" % (100 * zr)
        r["label"] = lab + zlab
        print("  %-9s %-22s 中位 %s s%s" % (who, lab, r["med"], zlab))

    json.dump(dict(roles=out, detail=detail), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出", OUT)


if __name__ == "__main__":
    main()
