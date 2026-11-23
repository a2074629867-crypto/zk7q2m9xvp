# 停顿链路打通（2026-11-15 01:2x）

此前状态：**生产链最后一个硬阻塞**。`pause_llm.json` 只有 Wonder 的 I/L 编号 33 条，
本书 `c*` 0 条判定 ⇒ 全量注入会 100% 落统计常数，直接违反需求 19-0。
`_pause_vote/p_a.jsonl` 那 1085 处是按标点类型规则铺的（why 全是「从句未完/并列/状语插入」），
对白覆盖 **0 条**，不能当 LLM 判定用。

现在这条链路通了。全流程与实测数字如下。

## 一、情境化任务包（`_pause_ctx.py`）

按用户要求「停顿要按当时情境 + 人物性格判」，给每处标点补三样输入：

| 输入 | 含义 | 覆盖 |
|---|---|---|
| `emo` | 该句情绪（人工台账已验收） | 239/239 |
| `scene` | 场景紧张度 0~1，**章内相对分位** | 高 90 / 中 86 / 低 63 |
| `role` | 角色画像，按该角色全部台词的情绪分布 | Thomas/Charles/Joseph 有效；Helena 标 `insufficient` |

- 第一版 `scene` 用绝对占比（同段 ±2 句里紧张类占比），结果 **179/239 全落「高」**
  —— 整部戏本来就激烈，绝对值没有区分度。改章内分位后才有高/中/低三档。
- prompt 里**不给判定阶梯**，改成「先定整句呼吸 → 叠性格基线 → 性格×情绪交叉」，
  并明确禁止把 `why` 写成语法标签。
- 产出 **20 包 / 239 条 / 567 处槽位**（`_ann/tasks_ctx/`）。

## 二、三路并行标注

三个模型各自独立标完 20 包（每路自跑 `_ann_check_one.py --tasks .../tasks_ctx` 自查，全 `[OK ]`）：

| 路线 | 批次 | 自查 |
|---|---|---|
| hy4 | 20/20 | 全 OK |
| ds | 20/20 | 全 OK |
| glm | 20/20 | 全 OK |

产出目录 `_ann/out_ctx/{hy4,ds,glm}/`。

## 三、投票与仲裁

```
G:/Python310/python.exe annotate_prosody.py merge \
  --dirs _ann/out_ctx/hy4 _ann/out_ctx/ds _ann/out_ctx/glm --out-dir _ann/merged_ctx
```

| 维度 | 三票一致 | 两票 | 分歧 | 至少两票率 |
|---|---|---|---|---|
| 停顿 | 346 | 215 | **6** | **98.9%（561/567）** |
| 重读 | 212 | 0 | 1 | 99.5% |
| 慢读 | 38 | 0 | 0 | 100% |

**只有 2 路时一致率 76.9%、131 处分歧**（无法裁决）；补第三路后分歧降到 6 处。
这就是「至少要三路」的实证。

6 处三方各执一词，逐条人工仲裁（`vote=arbitrated`，写回 `pause_ann.jsonl`）：

| bid | 裁定 | 理由 |
|---|---|---|
| `c1_0049#2` | short | 引语起点，说话动词后要换一层，短促换气 |
| `c1_0076#2` | short | 名字是信息落点，给一拍，但后面 taking 还接着走 |
| `c2_0299#7` | long | 话断在半空，后面那句他不肯说出口，空当就是意思 |
| `c2_0404#1` | mid | 归属说满停半拍再补 now；整句五词，长停会拖垮 |
| `c2_0443#2` | zero | `too` 贴上半句收尾，逗号不占时间 |
| `c2_0468#2` | short | 甩手话紧跟，但搬到「父亲」这个靠山前要极短断点 |

## 四、生产表

```
G:/Python310/python.exe pause_ann2llm.py \
  --ann _ann/merged_ctx/pause_ann.jsonl --texts _dlg_plan_v2.jsonl \
  --out pause_llm_castle.json
```

- 239 条台词 / **567 处**，`src=llm` **100%**（无一条回退常数），`why` 覆盖率 100%
- 对齐：原文缺 0 / 标点不符 0 / 序号异常 0
- 档位：beat 211 · tight 175 · clause 152 · drop 29（drop = 真连读）
- **96.8% 覆盖率是分母问题**：差的 19 处全是句末句号，本来就由音频自然收尾，不注入 ⇒ 可注入槽位 **100%**

## 五、注入

```
G:/Python310/python.exe mt_final_pause.py \
  --llm pause_llm_castle.json --texts _dlg_plan_v2.jsonl \
  --in _audio_ch123/out --out _audio_ch123/out_paused
```

`_audio_ch123/out_paused/` **239/239 条**，实测：

| 指标 | 结果 |
|---|---|
| 总时长 | 798.0s → **815.4s（+2.2%）** |
| 单条变化 | 中位 **+0.00s**，最大 +1.67s（`c3_0802`），最大压缩 −1.37s（`c2_0491`） |
| 时长未变 | 117 条（原本已经停够），变化 <0.1s 共 133 条，>0.5s 21 条 |
| voiced RMS | min −24.3 / 中位 −24.0 / max −23.5，**跨度 0.77 dB**（铁律 ≤1 dB ✓） |
| 峰值 | max **0.726**（无削波，soft_clip 上限 0.891） |

`c2_0491` 压缩最多是有依据的：Thomas 兴奋「报菜名」式炫耀，8 处全给 `tight 0.20`
（「第一间房说完就换下一间，显摆得不停脚」），不是参数错误。

## 六、三个坑（都踩了，都记下来）

### 1. 漏 `--texts` 会静默退回 ASR 标点

第一遍 dry 跑，输出写着 `asr 插 1处`、`标点命中 .=2` —— LLM 表**根本没生效**。
`mt_final_pause.py:495` 的注释自己就写了这件事：不给 `--texts`，`k in TEXTS` 为假，
`LLM 逐处判定` 与 `pause_intent` 两个分支都不执行，**标注等于没喂**。
加上 `--texts _dlg_plan_v2.jsonl` 后才变成 `llm 插 1处`。

### 2. `--in` 是整目录，会把旁白一起注入

第一遍没给 `--only`，它把 `_audio_ch123/out` 全部 955 条当输入，
已写出的 645 条里 **467 条是旁白**（按 c*/N* 前缀分不出来，得按 plan id 集合分）。
已全部删除重跑。旁白那 716 条目前**没有任何 LLM 停顿判定**，不能注入。

### 3. 强制对齐缓存的 key 带 size+mtime

`_wtlib.word_times_cached` 用 `basename|size|mtime` 做 key，所以回填音频后会自动重算——
这条**是对的**（对照闸 4 那个只按文件名命中的脏缓存，是反面教材）。

## 七、还差的

1. **旁白 716 条停顿未标注**：`p_a.jsonl` 是规则铺的，不能用。要么照这套补 20+ 包，
   要么接受「旁白不注入停顿」。
2. **真吞字清单**：注入时按 19f 判据跳过 `status=none` 的槽位（塞静音补不回 pitch reset），
   这些要进重生成。本次全量注入的完整清单在 `_audio_ch123/out_paused/_pause_report.json`
   的 `swallow` 字段（分批跑，最后一次只覆盖 63 条；全量需要重跑一次汇总）。
3. 注入后音频要重跑七闸（v32 已发起，`--dir _audio_ch123/out_paused`）。

## 八、复现命令（完整顺序）

```bat
G:/Python310/python.exe _pause_ctx.py --batch 12                     :: 20 包
:: 三路并行标注 → _ann/out_ctx/{hy4,ds,glm}/
G:/Python310/python.exe _ann_check_one.py --tasks G:/_setup/_ann/tasks_ctx --dir G:/_setup/_ann/out_ctx/hy4 --batches batch_0001 ... batch_0020
G:/Python310/python.exe annotate_prosody.py merge --dirs _ann/out_ctx/hy4 _ann/out_ctx/ds _ann/out_ctx/glm --out-dir _ann/merged_ctx
G:/Python310/python.exe pause_ann2llm.py --ann _ann/merged_ctx/pause_ann.jsonl --texts _dlg_plan_v2.jsonl --out pause_llm_castle.json
G:/Python310/python.exe mt_final_pause.py --llm pause_llm_castle.json --texts _dlg_plan_v2.jsonl --in _audio_ch123/out --out _audio_ch123/out_paused
```
