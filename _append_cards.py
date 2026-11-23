# -*- coding: utf-8 -*-
"""把今晚的结论追加进 DECISIONS.md / STATE.md（UTF-8，只 append，不改原文）。"""
import io, os

DEC = """\n\n## 2026-11-15 19:1x 旁白三路标注定稿 + F0 复核判负

1. **三路定稿**：`_ann/out_v3t/{ds,hy3,hy4}` 各 48/48 批（每路读回 716 句）；merge 到 `_ann/merged_v3`
   → pause **1079** / stress **1177** / rate **279**。三票一致 91.1% / 98.5% / 97.5%，
   至少两票 **100% / 98.7% / 98.9%**（验收线 70%）。秒数全部落旁白三档：
   0.51×468、1.135×544、1.695×67，**无 0.49/0.20 混入**（尺度没串轨）。
2. `pause_ann2llm` 落 `pause_llm_narr_v3.json`：**1079/1079 对齐、跳过 0**、覆盖 69.9%（本书 1543 槽位）。
3. `mt_final_pause` 只跑 `--dry`（插入 46 / 压缩 5 / 走批图退回 0）。**没有写任何音频**：
   旁白音频已验收，重注停顿是独立决定，要单独批准。
4. **第 15 项 F0 复核（641 条）判负**：双估计器都判突跳 = **0**；仅 parselmouth = 18（2.8%）；
   仅 pyin = 0；两者都无 = 623（97.2%）；中位 F0 > 305Hz = **0 条**。
   ⇒ 「高音帧」告警全是 parselmouth 跟踪噪声，**没有真缺陷，不重生成任何一条**。
   该改的是判据（改成双估计器一致才判 FIX），不是音频。
5. **跑批坑（已修进代码，别再重踩）**：
   - `tasks_v3*/INDEX.json` 顶层是 list，旧 glob 无条件当批次 → `run_batch` 里 `src["prompt"]` TypeError
     → 主线程 `f.result()` 重抛 → **全池当场崩**。症状是「满屏 502、只跑出个位数批次」。
     已修：glob 只吃 `batch_*.json`；单批载入包 try；主循环 `f.result()` 包 try。
   - `annotate_prosody.py merge` 在某一路缺 sid 时 `None.get("rate")` 崩。已加 `isinstance(it, dict)`。
6. **`usage.completion_tokens` 是网关累加计数器**，不是单次用量：11 秒报 97,352 token = 8800 tok/s，
   物理不可能，且产物只有 6 KB。**不许拿它当「思维链爆炸」的证据**，也不要据此调 prompt/maxtok。
7. **502/503 定性**：两个网关小请求全 200（5 个 lane 都通），502 只在大批次上偶发、换网关可自愈；
   503 `no_healthy_account` = 账号池冷却，并发越高越容易触发。⇒ 三路改**顺序执行 + `-j 2`** 后才跑完。
   `reasoning_effort` / `thinking.disabled` / `enable_thinking` / `chat_template_kwargs` 四个关思考参数
   **网关接受但无效果**。
"""

ST = """\n> ### 旁白三路标注定稿（2026-11-15 19:1x）
> - `_ann/out_v3t/{ds,hy3,hy4}` 各 **48/48 批 = 716 句**；`_ann/merged_v3`：
>   pause **1079** / stress **1177** / rate **279**，至少两票 **100% / 98.7% / 98.9%**
> - 秒数全落旁白三档（0.51×468 / 1.135×544 / 1.695×67），无对白尺度混入
> - `pause_llm_narr_v3.json`：1079/1079 对齐、跳过 0、覆盖 69.9%
> - `mt_final_pause` 仅 `--dry`（插 46 / 压 5 / 退回 0），**音频未动**
> - 第 15 项 F0 复核 641 条：双估计器都判突跳 **0 条**，中位 F0>305Hz **0 条** ⇒ 判负，不重生成
> - 跑批真因：`INDEX.json` 被当批次 → 全池崩（不是 502）；已修 glob + 异常隔离
"""

def append(path, text):
    if not os.path.exists(path):
        print("缺文件:", path)
        return
    with io.open(path, "a", encoding="utf-8") as f:
        f.write(text)
    print("追加完成:", path, os.path.getsize(path), "B")

append("G:/_setup/DECISIONS.md", DEC)
append("G:/_setup/STATE.md", ST)
