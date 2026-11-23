
---

## 2026-11-16 02:2x：云端容器失联；stress/rate 进生产链；旁白三档停顿注入（新目录）

### 1. AI Studio 容器已停（不是网络问题）

- 两条命令各等 200s 都没回传；回传 topic 用 `since=all` 拉也是 **0 条**
  ⇒ 不是「下载慢」，是**常驻执行器 w11.py 没了**（容器被回收 / 页面已关）。
- 后果：EmphaClass-en.tar.gz 的重下**停在中途**，进度未知（拿不到远端）。
- 恢复只有一条路：重开 `aistudio.baidu.com/project/edit/10844526`，在单元格里重启执行器。
- 附：EmphaClass 当重读检测器实测 **AUC 0.516 = 随机**（见 DECISIONS 末条），
  重下的价值只剩「留档」，不影响旁白链路任何判断。

### 2. stress / rate 两张表接进生产链（新脚本）

| 脚本 | 输入 | 输出 | 实测 |
|---|---|---|---|
| `stress_ann2llm.py` | `_ann/merged_v3/stress_ann.jsonl`（1177 条） | `stress_llm_narr.json` | **1177/1177 对齐、跳过 0**；686 句；强度 1档37 / 2档762 / 3档378；密度 11.7%（1 处 / 8.6 词）；sentence_type 由规则推（stmt 1169 / yesno 5 / wh 3），标 `rule:*`，不是标注 |
| `rate_ann2llm.py` | `_ann/merged_v3/rate_ann.jsonl`（279 句） | `rate_llm_narr.json` | 按 `_narr_blocks.json` 聚合到 81 块；四条硬约束 0 违反 |

- **rate 的诚实结论**：标注覆盖 45.5% 词，block 加权均值 **0.756~0.789，极差 0.032**
  ⇒ 句子级 rate 标注**没有块间区分度**，聚合只能得到「16 块 0.77 / 其余 0.80」；
  与现役 `_narr_rate_plan_castle.json`（人工 block 级，0.72/0.76/0.78）**差 24 块**。
  要真做 rate，得**按 block 重新标**，不是把句子级往上滚。
- stress 的用法边界（`_annot_legacy_inventory.md` §七.4）：标注只能**定位**该重读的词，
  能不能读到要靠生成后检测 + 抽 seed（历史命中 13%），所以它是 QA / 重生成清单，不是直接控制量。

### 3. 旁白三档停顿注入（真跑，输出到新目录）

- 命令：`G:/Python310/python.exe -u _run_pause_narr.py`
  即 `mt_final_pause --in _audio_ch123/out --out _audio_ch123/out_paused_narr
  --llm pause_llm_narr_v3.json --texts _narr_plan_for_pause.jsonl --who narrator --bed-self`
  `--only` 的 716 个 id 由 `_narr_ids716.json`（从 `_narr_phys_fix3.json` 导出）喂，
  避免撞 Windows 8191 命令行上限。
- **已验收的 `_audio_ch123/out` 一个字节没动**；注入结果全在新目录，闸门不满意就不采用。
- 试水 3 条（--dry）：插 6 处 / 时长 +18.8%；`--texts` 必须给，否则 `k in TEXTS` 为假、
  LLM 分支静默不执行（就是 11-15 那张 46/5 表看着对、其实没喂进去的原因）。
- ⚠ 实测约 **16% 的条目测不出自底噪**（句子短、凑不够 0.30s 连续安静帧），原代码会插**数字零**，
  违反 REQUIREMENTS 25a。已改 `mt_final_pause.py` 的 else 分支：改铺 `room_tone_panel.wav`
  （取自本库母带 wonder_train.wav 的 2700 个安静帧，真实房间声，不是 synth_bed 粉噪），
  报告记 `src=fallback`。**正在跑的那轮是旧代码**，收尾必须按日志里 `纹理none` 的 id 补跑。
