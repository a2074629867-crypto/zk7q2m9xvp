# STATE — 当前状态（每次会话开场必读，只写「现在在哪」）

> 更新时间：2026-11-25 15:55
> 2026-11-11 ~ 11-24 的 1096 行版本迭代史（v20→v50 全过程、旁白/EmphaClass/云端三段折腾）已归档：
> `G:/_setup/_archive/STATE_20261125_1096l.md`。本文件只留三样：**现在在哪 / 还活着的约束 / 去哪查**。
> 铁律看 `MEMORY.md`，走死的路看 `DECISIONS.md`，接手看 `F:/Charles/HANDOFF.md`。

## 项目：MintReader 旁白 + 对白 TTS 配音（The Castle of the King 前三章）

### 交付物
- 成品音频：`G:/_setup/_audio_ch123/out/` **955 wav / 561MB / 101.7 分钟**
- 旁白 716 / Thomas 110 / Charles 68 / Joseph 53 / Helena 8
- 旁白两版并存：`out`（人工验收版）/ `out_paused_narr`（三档停顿注入，物理闸同基线、数字零 0 帧）—— **换不换等 Charles 拍板，两边都别删**
- 对白停顿候选：`_pause_trim_llm/`（按 LLM 目标裁剪过，**未回填**）

### 当前数字（2026-11-25 15:50 复核，台账为准）

| 项 | 数 | 台账 |
|---|---|---|
| 旁白物理闸 | PASS 712 / WATCH 4 / FIX 0；−24.2dBFS、跨度 0.40dB | `_narr_phys.json` |
| 对白可听 | **193 / 239**（150 PASS + 43 短句 S_PASS） | `_gate_dlg_v50.json` + `_short_gate_v49.json` |
| 对白待处理 | **45**（38 非短句 MANUAL + 7 REGEN） | 同上 |
| 句内停顿超限 | **106 / 239** 条（LLM 目标表 567 槽：加长 91 / 剪短 86 / 已达标 112） | `_gap_all.json` + `pause_llm_castle.json` |
| 按目标裁剪结果 | 275 个可测边界：达标 122 / 仍超 89 / 不足 64；实剪 82 处、省 23.3s | `_edit_pause_dlg_report.json` |
| 语调超差 | 按现判据 >3.0 的 **0 条**（旧 18 条口径已作废） | `_inton_now.json` |

### 两条链路（判据与模型完全不同，不可互借）

| | 旁白链路 | 对白链路 |
|---|---|---|
| 判据 | 韵律/起伏（energy_span 带界、F0 持续高音帧、末段上扬、HNR） | **七闸**：声学 + 声纹 1-NN/Z-norm + emotion2vec + 句内一致 + 档内一致 + 自然度 |
| 脚本 | `narr_check.py` / `narr_gate_phys.py` | `dialog_gate.py`（挂 `gate_intra` / `gate_scs` / `gate_nat`） |
| 短句 | 不适用 | 走 `_short_gate.py`（双 ASR 仲裁，声纹/情绪免责） |

### 待办（做完一项改这里，别只改对话）

1. ☐ 回填 `_pause_trim_llm`（只剪静音、不碰 take；89 槽静音不够剪、64 槽不足要 edit）
2. ☐ 91 个槽要**加长** → 只能 edit 原生重渲染（涉 71 行）；**必须先剪后加**，顺序反了白做
3. ☐ 对白 45 条待处理（38 非短句 MANUAL + 7 REGEN）
4. ☐ 5 条延长音已选未回填：`c1_0015`→s42 / `c2_0368`→s44 / `c2_0279`→s43 / `c2_0309`→s44 / `c2_0372`→s42（备份 `_bak_elong_1125/` 就绪）
5. ☐ Thomas/Hopper **61 条 >260wpm** 超速重生成（重生成可降 30%，WSOLA 0.78 只能到 297 不够）
6. ☐ 噪声 A 组 **11 条**重生成（`_noise_stats2.py` 口径：A 11 / B 178 / C 50）
7. ☐ 真吞字清单汇总（旁白 57 处 + `EXPR=none` 85 条，单次报告只覆盖过 63 条）

### 下一步
**先回填 `_pause_trim_llm`（纯剪静音、可逆），再开 edit 那 71 行加长 —— 反序会白跑一遍。**

### 还活着的约束（每条都因踩过才留）

- **插停顿必须给 `--texts`**：不给则 `k in TEXTS` 为假、LLM 分支**静默不执行**（曾让一张 46/5 的表看着全对、其实一处没喂进去）。
- **停顿键两个索引体系**：`pause_llm*.json` 的 key 是 wav stem，value key 是**标点序号（1 起）**；`pause_llm` 要的是 **token 下标（0 起）**。必须 `parse_text` 重对齐，直接转会插到半句话中间且不报错。
- **底噪**：`mt_final_pause` 默认 `--bed` 关闭（合成粉噪在长停顿处比真空还假）；**不许数字零** —— 旧 `out` 有 1091 帧 / 258 条违规；测不出自底噪时铺 `room_tone_panel.wav`，报告记 `src=fallback`。
- **旁白条内停顿**：逗号 **0.70** / 句号 **0.85**；1.16 / 1.53 是**条间**档。把条间值铺到条内会让弱标点比强标点还长（用户当场纠正过）。
- **rate 单位 = 句子（一个 wav 一句），base 1.00 原速**。0.80 / 0.90 两次被否（"整本慢"）；块级 `rate_*_scene_v1.json` 已 `_void`，只作统计。
- **旁白声纹只能整条提嵌入**：按静音切段再补长到 2s 后，同句内 0.432 vs 不同句 0.450（差值 −0.018，无区分力）。整条口径零分布中位 0.741，验收 ≥0.65。
- **EmphaClass 长度不变性不成立**：同一 5s 窗放在 20s 句里判 0.00、单独跑 0.086 ⇒ 只认固定 5s 叶片；它当"重读检测器" AUC 0.516 = 随机，**该用途作废**。
- **重跑对白全量闸**必须 `--lib _emo_refs_all.json --bg-map "@_bg_map.json"`，否则 Z-norm 混域出假分层（曾跑出 A 98 / D 87）。
- **对白侧闸 6 的 z 阈值不能套旁白**：`COL` sd 0.176 vs 0.489，z 放大 2.8 倍，曾把 21 条 NISQA 明显变好的音频判死 19 条。
- 用户红线（tempo 0.70 / 声纹 0.65 / 电平 voiced RMS / 不拆句不吞字 / 省略号只拉元音 / 口吃≠停顿 / 等响 / 人耳终审）见 `HANDOFF.md` 第二节，本节不重复。

### 环境卡点（会反复咬人）
- `G:/Python310/python.exe` 是唯一同时有 onnxruntime + torch + parselmouth 的解释器
- `dialog_gate.py` 必须 `PYTHONPATH="G:/_setup;G:/_setup/emo_bench"`
- 模型池会整体 503 冷却（per-model cooldown），重试无效 ⇒ 改在环里判
- RX580 8G：Vulkan 必 OOM，只能 `--threads 2 + mem_saver=true`

### 去哪查

| 要什么 | 去哪 |
|---|---|
| 现在在哪、下一步第一件事 | `F:/Charles/HANDOFF.md`（11-25 重写，83 行） |
| 为什么这么做 / 哪些路已走死 | `G:/_setup/DECISIONS.md` |
| 验收 29 条 | `G:/_setup/REQUIREMENTS.md` |
| 两周硬教训（10 条） | Skill `dots-tts-dubbing` §18.47 |
| 本文件历史（1096 行） | `G:/_setup/_archive/STATE_20261125_1096l.md` |
| 一跑就打印我 | `G:/Python310/python.exe G:/_setup/resume.py` |
