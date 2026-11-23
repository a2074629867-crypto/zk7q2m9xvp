# -*- coding: utf-8 -*-
"""_narr_pause_build.py —— 旁白停顿：投票 → 生产表（一键，可反复跑）

三路实际落地情况（2026-11-15 凌晨，如实记录）：
  hy3  → `_ann/out_narr/hy3`（25 条/批，20 批，全过自查）
  ds   → `_ann/out_narr8/ds`（8 条/批，63 批）— 7863 聚合网关大批次会 502，改小批
  mm   → `_ann/out_narr8/mm`（8 条/批，63 批）— **原定 HY4 通道实测单批 4 分钟
         （8 条要 6 万+ 思考 token），63 批约 4 小时，超出夜间窗口；第三路改用
         MiniMax-M3.1-Flash，同样是独立模型族，投票意义不变。**

用法：
  G:/Python310/python.exe _narr_pause_build.py
  G:/Python310/python.exe _narr_pause_build.py --allow-missing   # 允许少于三路（会写进报告）
"""
import argparse
import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
from _ann_check_one import check_one

HERE = "G:/_setup"
LANES = [
    ("hy3", os.path.join(HERE, "_ann", "out_narr", "hy3"),
     os.path.join(HERE, "_ann", "tasks_narr_ctx")),
    ("ds", os.path.join(HERE, "_ann", "out_narr8", "ds"),
     os.path.join(HERE, "_ann", "tasks_narr_ctx8")),
    ("mm", os.path.join(HERE, "_ann", "out_narr8", "mm"),
     os.path.join(HERE, "_ann", "tasks_narr_ctx8")),
]
MERGED = os.path.join(HERE, "_ann", "merged_narr")
# ★ 本书里有些「旁白行」的 speaker 是 Joseph/Edmund/Helena（她们在叙述里被点名），
#   直接用原 plan 喂 merge，track_of_speaker 会把这些旁白判成 dlg 轨，
#   套上 0.20/0.49/0.68 的对白尺度 —— 实测 4 条 37 处中招。所以用强制 narrator 版。
TEXTS = os.path.join(HERE, "_narr_plan_for_pause.jsonl")
OUT = os.path.join(HERE, "pause_llm_narr.json")
PY = "G:/Python310/python.exe"
BAN = ["从句边界", "一般短语间", "并列", "状语", "语法", "标点类型", "句法"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-missing", action="store_true")
    a = ap.parse_args()

    ready, ok_lanes = True, []
    for lane, d, tasks in LANES:
        batches = sorted(x for x in os.listdir(tasks) if x.startswith("batch_"))
        miss, bad = [], []
        for b in batches:
            p = os.path.join(d, b)
            if not os.path.exists(p):
                miss.append(b)
                continue
            errs, _n = check_one(d, b, tasks)
            if errs:
                bad.append((b, errs[:2]))
        print("  %-4s 批 %d｜缺 %d｜格式错 %d" % (lane, len(batches), len(miss), len(bad)))
        for b, e in bad[:3]:
            print("      错", b, e)
        if not miss and not bad:
            ok_lanes.append(lane)
        else:
            ready = False
    if not ready and not a.allow_missing:
        print("\n还没齐。补跑：")
        print("  %s _ann_llm_run.py --tasks _ann/tasks_narr_ctx8 --out-root _ann/out_narr8 "
              "--lanes ds mm -j 2 --gw http://127.0.0.1:7863/v1/chat/completions" % PY)
        return 1
    if len(ok_lanes) < 2:
        print("至少两路才能投票，现在 %s" % ok_lanes)
        return 1
    print("参与投票：%s" % ok_lanes)

    print("\n=== 合并投票 ===")
    dirs = [d for lane, d, _t in LANES if lane in ok_lanes]
    cmd = [PY, os.path.join(HERE, "annotate_prosody.py"), "merge",
           "--dirs"] + dirs + ["--out-dir", MERGED, "--texts", TEXTS]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((r.stdout or "")[-2000:])
    if r.returncode != 0:
        print("merge 失败:", (r.stderr or "")[-800:])
        return 1

    print("\n=== 转生产表 ===")
    cmd = [PY, os.path.join(HERE, "pause_ann2llm.py"),
           "--ann", os.path.join(MERGED, "pause_ann.jsonl"),
           "--texts", TEXTS, "--out", OUT]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((r.stdout or "")[-2500:])
    if r.returncode != 0:
        print("转换失败:", (r.stderr or "")[-800:])
        return 1

    rows = [json.loads(l) for l in open(os.path.join(MERGED, "pause_ann.jsonl"), encoding="utf-8") if l.strip()]
    c_tier = collections.Counter(r.get("mark") for r in rows)
    c_vote = collections.Counter(r.get("vote") for r in rows)
    nb = [r for r in rows if any(b in (r.get("why") or "") for b in BAN)]
    print("\n=== 质量 ===")
    print("  槽位 %d ｜ 档位 %s ｜ 投票 %s" % (len(rows), dict(c_tier), dict(c_vote)))
    print("  含语法标签 why %d 条（%.1f%%）" % (len(nb), 100.0 * len(nb) / max(1, len(rows))))
    print("  why 平均 %.1f 字" % (sum(len(r.get("why") or "") for r in rows) / max(1, len(rows))))
    ag = json.load(open(os.path.join(MERGED, "agreement.json"), encoding="utf-8"))
    print("  一致率 %s" % json.dumps(ag, ensure_ascii=False))
    print("\n生产表 → %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
