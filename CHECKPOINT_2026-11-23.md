# 断点存档 — 2026-11-23 20:26（旁白全库按新标准重生成 + 重音回环）

> 恢复方式：先读本文件，再按「未完成」段的第一条命令继续。所有步骤都可重入，重跑不会重复劳动。

---

## 一、已完成（可直接用，不要再跑一遍）

### 1. 全量重生成 716/716 ✅
- 目录 `G:/_setup/_regen_1123/`，台账 `_regen_1123.jsonl`
- **0 失败**，用时 16.27h
- rate：1.00 × 591、0.84 × 125（来自 `_castle_en_ch123_plan_v2.jsonl`）
- 不加 stress 标签、不插停顿

### 2. 物理闸 ✅ FIX 清零
```
PASS 703 (98.2%) / WATCH 13 (1.8%) / FIX 0
电平中位 −24.1 dBFS，跨度(p95−p5) 0.30 dB（要求 ≤1.0）
语速 p10/p50/p90 = 168 / 213 / 260 wpm
```
- 结果 `_narr_phys_regen1123.json`
- 首轮 9 条 FIX 已修：`_gate_fix.py --seeds 51,52 --apply`，9/9 采纳
  - 原 take 备份在 `_gate_fix/old/`，报告 `_gate_fix_report.json`
  - c3_0734 由 FIX→WATCH（语速 306），其余 8 条 PASS
- **剩 13 条 WATCH 全是「语速 >300 wpm」，都是 1 秒左右的短句，属提速后的自然结果，不修**

### 3. 词级 ASR ✅
- `_wl_regen1123.json`，716 条（已按 sid 归并，绝对路径键，0 缺失）
- 耗时 5.5 分钟

### 4. 重音再测（第 3 步）✅
| 口径 | 旧库 0.80 | 新库 |
|---|---|---|
| AUC | 0.726 | **0.682** |
| 副词平均分位 | 72.2% | **67.6%** |
| rel_z 均值 | +0.828 | **+0.412** |
| ≥1.6 | 37 (26%) | 17 (12%) |
| <0（读平） | 34 (24%) | **43 (30%)** |

- 结果 `_stress_adv_after.json`；旧库基准 `_stress_adv_before.json`
- **已验证不是提速导致**：z_sd 1.325→1.283（比 0.968，非量化衰减）；
  整条时长比 0.778（提速确实发生）；rel_z 是句内比值，等比拉伸数学上不改它
  ⇒ 掉的是「换了一代生成」，详见 `DECISIONS.md` 2026-11-23 条

### 5. 回环目标清单 ✅
- `_loop_targets.json`：40 条（z<0 的强调副词实例），`never` 占 13 条

### 6. 三档停顿 ✅
- `_regen_1123_paused/`，716 条
- **704/704 槽位插入成功**（plan 704、del 229 重叠槽）
- 合计增加 312.1 秒；报告 `_pause_regen1123_report.json`
- 51% 的槽位原本静音为 0（快语速下句内没留白），工具仍完成拼接插入

### 7. 两个页面 ✅
- `_narr_full_listen.html`（1358.6 KB，716 行，slow 125，missing 0，fallback 0）
- `_speed_ab.html`（402.3 KB，716 行，**平均 135.5 → 160.0 wpm，+18%**）
- 服务：`G:/Python310/python.exe -m http.server 8811 --bind 127.0.0.1 --directory G:/_setup`
  然后开 `http://127.0.0.1:8811/_narr_full_listen.html`

---

## 二、未完成（从这里继续）

### ① 回环第 4 步：抽 seed 重出失败项（进度 1/120）
```bash
G:/Python310/python.exe -u G:/_setup/_loop_1123.py --stage repick --limit 40 --seeds 43,44,45
```
- 已完成 1 个 take：`_loop_takes/s43/c2_0400.wav`
- 剩余 119 个 take，单个 66–150s ⇒ **约 3–4 小时**
- 产物写 `_loop_pick/`，**不覆盖** `_regen_1123/`
- 报告 `_loop_pick_report.json`，采纳条件：z 比现状高 0.30 以上且 ≥0.60、吞字 ≤1 个

### ② 采纳后要补的三件事（第 4 步跑完才有意义）
1. 把 `_loop_pick/*.wav` 写回 `_regen_1123/`（先备份）
2. 只对改动过的 id 重跑停顿：`_run_pause_1123.py` 目前是全量，需要加 `--only`
3. 重建 `_narr_full_listen.html`

### ③ 可选（未做，等指令）
- 13 条语速 WATCH 是否处理
- `_audio_ch123/out` 现役库是否正式换成新库（现在只在新目录，未替换）
- 第二章单章页 `_narr_ch2_listen.html` 仍是旧音频，未重建

---

## 三、今天踩的两个坑（已修，别再踩）

1. **`regen_narr.py` 的 `--out` 必须传绝对路径**
   `call_tts` 用 `cwd=ACPP_DIR` 起 audiocpp，相对路径会被写到
   `.../reader/_tts_lab/acpp/` 下面。今天因此白跑 5 个 take（20:04–20:23）。
   `_loop_1123.py` 已改成 `os.path.join(ROOT, "_loop_takes", "s%d")`。

2. **`narr_gate_phys.py --out` 也必须是绝对路径**
   相对路径时 `os.path.dirname()` 为空串，`makedirs('')` 直接崩（闸本身已跑完，只是写盘失败）。

---

## 四、关键文件索引

| 文件 | 作用 |
|---|---|
| `_regen_all_1123.py` | 全量重生成驱动（断点续跑，已完成） |
| `_gate_fix.py` | 物理闸 FIX 项换 seed 重出（已完成） |
| `_loop_1123.py` | 四步回环（asr / test / plan / repick） |
| `_chain_1123.py` | 守望器（本轮已用完，可留作下次） |
| `_stress_adv.py` | 副词重音测量（`--only` 可限定 sid 集） |
| `_diag_relz.py` | 判「真掉」还是「量具压平」 |
| `_run_pause_1123.py` | 新库三档停顿注入 |
| `_build_narr_ch2.py` | 试听页构建（`--chapter all --only716 --rates _rate_narr_v2.json`） |
| `_build_speed_ab.py` | 速度 A/B 页（全量增量刷新） |
| `_rate_narr_v2.json` | 新 rate 表（1.00×591 / 0.84×125） |

---

## 五、22:40 新发现：整本书少了 10 句旁白

`_narr_plan_for_pause.jsonl` 有 **726** 条旁白，但交付集 `_narr_ids716.json` 只有 **716** 条。
差的 10 句全部是**正文里带弯引号（‘ ’）**的：

```
c1_0027 c1_0049 c1_0105 c1_0167
c2_0251 c2_0267 c2_0326
c3_0797 c3_0944 c3_0953
```

**原因**：早期 `tokens+puncts` 拼接在弯引号上失败 ⇒ `pause_llm_narr_v3.json` 对它们给了 0 个槽位
⇒ 没进 `out_paused_narr` ⇒ 没进 716 交付集。

**现状**：这 10 句在 `_audio_ch123/out` 里只有干声（0.80 降速版），
在新库 `_regen_1123/` 里**完全没有**，所以新页面（限定 716）会把它们整句漏掉。

**处置脚本已写好**：`_fix_missing10.py`（重生成 → 插停顿 → 重建成 726 句）。
**等抽 seed 跑完再执行**（避免抢 GPU）。

> 注意：这 10 句没有内部停顿标注，插停顿只会做 trim+归一，听感会比其余句子更「一口气」。
> 要真正修好停顿，得对它们重跑 pause 标注（`_pause_ctx_narr.py`），那是另一件事。

---

## 六、2026-11-24 04:20 状态（云端放弃，回本地收尾）

### 云端 GPU（百度 AI Studio V100 16G）

实例**第二次起不来**。`RECOVERY_CLOUD.md` 已记同一症状：切 GPU 要先同步 `/home/aistudio`
全量文件并建索引，文件数一多就卡死。按「同一堵墙不磨第三次」⇒ **云端路线关闭**，
`rcc.py` 通道实测返回空（容器没起、`w11.py` 也不在）。云端资产保留，不再投入时间。

### 第 4 步（抽 seed）已完成

- **117 / 120 take**（39 句 × 3 seed），单条 91–97s，共约 2.5h
- 首次评分 **采纳 0/39** 是 bug，不是结果：`_loop_1123.py` 把 ASR 键按 basename 压成
  `c1_0011`，查询却用 `c1_0011_s43`，三个 seed 目录同名文件 ⇒ seed 维度被丢
- 修法：键改 `s43/c1_0011`，加 `--pick-only`（跳过生成只重评）
- **修后实测：采纳 5 / 39**
  c1_0143 +0.74(s43) / c1_0189 +1.63(s44) / c2_0504 +0.76(s43) /
  c3_0585 +1.08(s43) / c3_0771 +1.97(s45)

### 正在跑（后台 mTTZhc）

1. `_fix_missing10.py` —— 10 句弯引号缺口重生成（10 × 95s ≈ 16min）
2. `_apply_picks.py --apply` —— 写回 5 个采纳 take + 重跑 ASR + 重插停顿 + 重建页面

### 注意

- `+0.27` 是 80ms 时间戳量化的固定格点，多句重复出现属正常，不是数据错误
- 采纳阈值「现状 +0.30 且 ≥0.60」**不要为了好看调低**，0.30 ≈ 一个量化格点

---

## 七、2026-11-24 11:12 语速按真人母带校准完成（当前交付版本）

**最终交付目录：`G:/_setup/_regen_final`（726 条）**

| 项 | 值 |
|---|---|
| 句中语速 p10/p50/p90 | **152 / 178 / 188 wpm**（真人母带 127/175/227） |
| 落在 175±12% 带内 | 84%（旧库 51%，1.00 原速 40%） |
| 物理闸 | **PASS 716 / WATCH 0 / FIX 0** |
| 电平 | 中位 −24.1 dBFS，跨度 0.20 dB |
| 停顿 | 678/678 槽位插入，+290.7s |
| 重音（剪静音口径） | AUC 0.695（归一前 0.664），≥1.6 共 14 处 |

链路：`_regen_1123` →`_speed_norm.py`→ `_regen_1123_norm` →`_run_pause_1123.py`→
`_regen_1123_norm_paused` →`_level_fix.py`→ →`_tail_fix.py`→ `_regen_final`

页面（服务 `python -m http.server 8811 --directory G:/_setup`）：
- `_speed_calib.html` 三列对照（旧 0.80 / 新 1.00 / 归一后），17 句
- `_narr_full_listen.html` 全库 726 句
- `_narr_ch2_listen.html` 第二章 217 句
- `_speed_ab.html` 新旧 A/B（167.9 → 174.3 wpm）

**未做**：29 条仍偏快（最狠 233 wpm，被 0.72 下限兜住）；74 条 0.84 慢读档故意慢。
两者都在真人 p10–p90 之内，未再处理。
