# -*- coding: utf-8 -*-
"""追加当日工作日志（UTF-8 append）。"""
import io

P = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory/2026-11-15.md"
TXT = """
## 19:0x 旁白三路标注定稿 + 第 15 项 F0 判负

**跑批真因（不是 502，是脚本自己崩）**：`tasks_v3*/INDEX.json` 顶层是 list，`_ann_llm_run.py`
旧 glob 无条件当批次 → `run_batch` 里 `src["prompt"]` TypeError → 主线程 `f.result()` 重抛 →
全池崩。表现是「满屏 502、每次只跑出个位数批次」。已修：glob 只吃 `batch_*.json`、单批载入包 try、
主循环 `f.result()` 包 try、503 用长退避（20+15k，cap 90s）。

**502/503 定性**：两网关小请求全 200（5 lane 都通）；502 只在大批次偶发、换网关可自愈；
503 `no_healthy_account` = 账号池冷却，并发越高越易触发 ⇒ 三路改**顺序执行 -j 2** 后跑完。
`reasoning_effort`/`thinking.disabled`/`enable_thinking`/`chat_template_kwargs` 网关接受但无效果。
`usage.completion_tokens` 是**累加计数器**（11s 报 97k = 8800tok/s 物理不可能，产物仅 6KB），
不能当单次用量或思维链证据。

**结果**：`out_v3t/{ds,hy3,hy4}` 各 48/48 = 716 句 → `_ann/merged_v3`
pause 1079 / stress 1177 / rate 279；两票 100/98.7/98.9%，三票一致 91.1/98.5/97.5%；
秒数全落旁白三档（0.51×468 / 1.135×544 / 1.695×67）。
`pause_ann2llm` → `pause_llm_narr_v3.json`：1079/1079 对齐、跳过 0、覆盖 69.9%。
`mt_final_pause` 只 `--dry`（插 46 / 压 5 / 退回 0），**音频一律没动**。

**第 15 项 F0 复核（641 条）判负**：双估计器都判突跳 0 条；仅 praat 18 条（2.8%）；
中位 F0>305Hz 0 条 ⇒ 告警全是 parselmouth 跟踪噪声，无真缺陷、不重生成。

**另修**：`annotate_prosody.py merge` 在某一路缺 sid 时 `None.get("rate")` 崩，
已加 `isinstance(it, dict)` 判断（三路不全时必踩）。

**等拍板**：① 是否把三档停顿真注入 `_audio_ch123/out`（会改已验收音频）；
② stress/rate 两表怎么进生产链（只有 pause 有转换器）；③ F0 判据是否改双估计器一致才 FIX。
"""

with io.open(P, "a", encoding="utf-8") as f:
    f.write(TXT)
print("追加完成", P)
