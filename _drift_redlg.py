# -*- coding: utf-8 -*-
"""_drift_redlg.py —— 用对白版判据（profile="dlg"）重算 239 条对白的漂移缓存

背景：`_drift_cache.json` 原先是旁白判据（profile="narr"）算的，
      把表演对白的正常语调（ΔF0 p95 8.9 半音）当成了「音色阶跃」，
      导致长句 WARN 率 82%、而真正的声道形状突变（c1_0158）被判 PASS。

本脚本：全量重算 → 写回 `_drift_cache.json`（每条带 profile 字段）
        → `gate_intra` 的 profile 断言才能通过，不必每次实时重算。

用法：G:/Python310/python.exe _drift_redlg.py
"""
import sys, os, json, shutil
from datetime import datetime

sys.path.insert(0, r"G:/_setup")
os.chdir(r"G:/_setup")
import soundfile as sf
import mt_seg_drift as D

CACHE = "_drift_cache.json"
PROFILE = "dlg"

old = json.load(open(CACHE, encoding="utf-8"))
print("旧缓存 %d 条" % len(old))

out, err = [], []
for i, x in enumerate(old, 1):
    p = x["file"]
    try:
        if not os.path.exists(p):
            err.append((p, "文件不存在"))
            continue
        r = D.one(p, profile=PROFILE)
        # 保留旧判决用于对比
        r["old_verdict"] = x.get("verdict")
        r["old_events"] = x.get("events")
        out.append(r)
    except Exception as e:  # noqa: BLE001
        err.append((p, repr(e)))
    if i % 40 == 0 or i == len(old):
        print("  %d/%d" % (i, len(old)), flush=True)

print("成功 %d / 失败 %d" % (len(out), len(err)))
if err:
    for p, e in err[:10]:
        print("  ERR", os.path.basename(p), e)

# 写回（先备份一次带时间戳的，防手滑）
if os.path.exists(CACHE):
    bak = CACHE.replace(".json", "_prev_%s.json" % datetime.now().strftime("%m%d_%H%M"))
    shutil.copy(CACHE, bak)
    print("已备份 ->", bak)

json.dump(out, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("写出", CACHE, "%.1f KB" % (os.path.getsize(CACHE) / 1024))

from collections import Counter
print()
print("旧:", dict(Counter(x.get("old_verdict") for x in out)))
print("新:", dict(Counter(x["verdict"] for x in out)))

print()
print("=== 判决变化 ===")
for x in out:
    if x.get("old_verdict") != x["verdict"]:
        print("  %-10s %5.1fs  %-13s -> %-13s" % (
            os.path.basename(x["file"])[:-4], x["dur"], x.get("old_verdict"), x["verdict"]))
