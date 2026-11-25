# -*- coding: utf-8 -*-
"""按新口径（静音帧底噪 floor_q + snr_q + zero_ms）给 239 条重新分层。

旧分层（p10 口径）已作废：
  「必须重生成 69 / 可后处理 157 / 已合格 13」—— p10 在高语音密度条目上系统性报高，
  实测误报 96/190（一半）。
"""
import json
import os

d = json.load(open("G:/_setup/_noise_stats2.json", encoding="utf-8"))["dlg_out"]
rows = {k: v for k, v in d.items() if "floor_q" in v}

# 硬门槛（与 _dn_selftest 注入标定一致）：噪声混在人声里就救不回来 → 重生成
REGEN = []       # snr_q < 33 或 floor_q > -50（后处理压不下去）
FILL = []        # 有数字零 或 floor_q 在 -60~-50（统一底噪能救）
OK = []
for k, v in rows.items():
    if v["snr_q"] < 33 or v["floor_q"] > -50:
        REGEN.append((k, v))
    elif v["zero_ms"] > 10 or v["floor_q"] > -60:
        FILL.append((k, v))
    else:
        OK.append((k, v))

print("总 %d 条" % len(rows))
print("  A 必须重生成（snr_q<33 或 floor_q>-50）: %3d 条" % len(REGEN))
print("  B 统一底噪可救（数字零 / floor -60~-50）: %3d 条" % len(FILL))
print("  C 已合格: %3d 条" % len(OK))
print("  合计 %d" % (len(REGEN) + len(FILL) + len(OK)))
print()
print("A 组明细:")
for k, v in sorted(REGEN, key=lambda x: x[1]["snr_q"]):
    print("  %-9s snr %5.1f floor %6.1f zero %6.0fms dense %.2f"
          % (k, v["snr_q"], v["floor_q"], v["zero_ms"], v["dense"]))

open("G:/_setup/_regen_hard_ids.txt", "w").write("\n".join(k for k, _ in REGEN))
open("G:/_setup/_postfix_ids.txt", "w").write("\n".join(k for k, _ in FILL))
print("\n-> _regen_hard_ids.txt (%d) / _postfix_ids.txt (%d)" % (len(REGEN), len(FILL)))
