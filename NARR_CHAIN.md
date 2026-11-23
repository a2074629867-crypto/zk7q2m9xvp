# 旁白链路 — 全部生产工具与功能清单（2026-11-15 12:35 实测）

> 口径：本页所有数字都是**当场查磁盘/跑脚本**得到的，不是从旧台账抄的。
> 唯一权威判据来源：脚本本身 + `_narr_phys_now.json`（12:23 对当前磁盘重算）。

## 0 一句话现状

十三个环节的**脚本全部存在**，`_chain_audit.py` 体检报「全部打通」——但那是**文件存在性**检查，
不代表判据干净。真实情况是：**生成→物理闸这一段干净（PASS 712/716，FIX 0），
LLM 投票这一段做了一个空壳（stress 0 槽），标注结果没有被生产链吃进去（v5 绕过），
重生成没有驱动（人工点单）**。所以「完整闭环」还差三个焊点，见 §2。

---

## 1 十三个环节（脚本 → 功能 → 输入/输出 → 现状）

| # | 环节 | 脚本 | 功能 | 输入 → 输出 | 现状 |
|---|---|---|---|---|---|
| 1 | 分块 | `mk_narr_blocks.py` (58行) | 按章切块，一块=一次 TTS 调用 | `_narr_text` → `_narr_blocks.json` | OK |
| 2 | 计划 | `mk_narr_plan_v3.py` (200行) | 逐块定 `<rate>` 慢读系数、目标 wpm | blocks → `_narr_plan_v3.json` | OK |
| 3 | 生成 | `narr_chain_run.py` (118行) | dots.tts 出块音频；**块内只允许一个 `<rate>` span**（实测唯一不丢词的写法） | blocks+plan → `_narr_new/raw` | OK |
| 4 | 后处理 | `narr_post.py` (195行) | trim 首尾静音（HEAD 0.06/TAIL 0.10）→ rubberband 变速 → 归一 | raw → `out` | OK（但 `CL.clean` 的 `rms_voiced_db` 是算术平均 dB，**不能用来归一**，见 §3.1） |
| 5 | 物理闸 | `narr_gate_phys.py` (192行) | 硬切/语速/电平/削波 四硬项 | wav → `_narr_phys_*.json` | **PASS 712 / WATCH 4 / FIX 0**（`_narr_phys_now.json`） |
| 6 | 韵律层 | `narr_check.py` (487行) | energy_span 带界、F0 高音帧（pyin ≥8 帧）、末段上扬、HNR | wav → 判档 | ⚠ 判决**不落盘**，只写 FIX 名单；且在**当前音频上没复跑**（见 §2 P1-3） |
| 7 | 本地修 | `fix_narr3.py` (142行) | 补尾静音 / 软限幅 / 重归一，不重生成 | wav 原地 | OK（11-12 修过 3 条，备份 `out_bak_fix3`） |
| 8 | 重生成 | `regen_narr.py` (157行) | 纯文本+seed 生成 → trim → rubberband → 能量平均归一到 −24 | `--ids` → `_regen_narr_out/` | ⚠ 可用但**只吃手写 id**，单条 **4.9 分钟**（c1_0054 实测 293.9s） |
| 9 | 建标注包 | `annotate_prosody.py build --only narr` | 出任务包（prompt 含 pause 三档 + stress + rate） | 文本 → `_ann/tasks_v3`（**48 包 / 716 句 / 12:13 建**） | OK，包已就绪 |
| 10 | 跑标注 | `_ann_llm_run.py` (182行) | 三路并发调 LLM，带自查重试 | tasks → `out_full/narr/<lane>` | lane 已定 `hy4`(global:hy4free) / `hy3`(global:hy3) / `ds`(deepseek-v4.1-flash-sg) |
| 11 | 投票合并 | `annotate_prosody.py merge --dirs ...` | 三路按 bid/tok 投票，`len<2` 不算共识 | 多路 → `merged*/{pause,stress,rate}_ann.jsonl` + `agreement.json` | ⚠ `_ann/merged_narr`：pause **1116 行**、rate **16 行**、**stress 0 行** |
| 12 | 转生产表 | `pause_ann2llm.py` (162行) | 标注 `bid=c1_0001#3`（1 起）↔ 生产 key（0 起 token 下标）两套编号对齐 | jsonl → `pause_llm_narr.json`（**499 行**） | OK（对齐有逐条标点校验） |
| 13 | 注入/重铺 | `mt_final_pause.py` (869行) / `_repause_v5.py` (171行) | 插静音 + 底噪匹配 / 按标点重铺条内停顿 | 音频+表 → `_audio_narr_paused/`（726 条）或 `out_v5`→`out` | ⚠ 两条路并存且**互斥**，见 §2 P0-2 |

### 诊断/取证工具（不产交付件，但都会影响判断）

| 脚本 | 功能 | 实测结论 |
|---|---|---|
| `_chain_audit.py` | 一屏看「哪些环节有输入、哪些断了」（只读文件规模） | 16 项全 OK（是存在性，不是判据） |
| `_gap_cand.py` | 找条内静音候选（用于重铺/注入的前置定位） | OK |
| `_narr_pause_build.py` | 从标点槽位置生成重铺计划 | OK |
| `_narr_pause_ab.py` / `_narr_drift_ab.py` | 停顿改动前后 A/B（时长/漂移） | OK，`_narr_drift_ab.json` 119KB |
| `_stress_loop3.py` | 重音闭环：三轴（dur/f0/eng）对 LLM 标注重读算 AUC | **时长 0.715 / F0 0.577 / 能量 0.568** |
| `f0_crosscheck.py` | praat vs pyin 双估器交叉验 F0 突跳 | 641 条，**FIX 130 条里 pyin 突跳 0 条** |
| `_narr_timbre.py` / `_narr_timbre_whole.py` | 音色一致性（整条 vs 切段） | 已验证：**句内切段不可用**，只能整条 |
| `emp_infer_local.py` / `_emp_analyze.py` | EmphaClass 重读分类器推理与分析 | 716 条全跑完，**AUC 0.516** |
| `_nat_guard.py` / `gate_nat.py` | 自然度下限（NISQA-MOS/DIS/COL + SQUIM-SUBJ，阈值 −2.3σ） | 只能筛「明显不行」，不能排序 |
| `_verify_v5.py` | 重铺后快速核对（条数/时长/峰值） | OK |

---

## 2 三个必须焊的断点

### P0-1 重读维度是空的：merged 的 `stress_ann.jsonl` = **0 行**

实测各路原始输出的 stress 槽：

| 目录 | 句数 | pause 槽 | **stress 槽** | 时间 |
|---|---|---|---|---|
| `_ann/out_full/narr/ds` | 716 | 1079 | **1103** | 11-12 |
| `_ann/out_full/narr/hy4` | 40 | 61 | 74 | 11-12 |
| `_ann/out_narr/hy3` | 524 | 1164 | **0** | 11-15 02:28 |
| `_ann/out_narr8/ds` | 499 | 1116 | **0** | 11-15 02:54 |
| `_ann/out_narr8/mm` | 499 | 1116 | **0** | 11-15 03:10 |

⇒ 11-15 那批 `tasks_narr8`（只问停顿）跑出来的三路**没有 stress**，
merge 后 `agreement.json` 里 stress 全 0、`stress_ann.jsonl` 空文件。
**投票机制没坏，是喂进去的包没问重读。**

**修法（已具备、未执行）**：`_ann/tasks_v3`（48 包 / 716 句 / prompt 已含 stress + 三档秒数）直接三路跑：

```
G:/Python310/python.exe _ann_llm_run.py --tasks _ann/tasks_v3 --out-root _ann/out_full/narr --lanes hy4 hy3 ds -j 2
```

### P0-2 标注结果没进生产：v5 把「LLM 选址」留下、把「三档时长」换成了常量

- `_repause_v5.py` 头部写死：`COMMA, PERIOD = 0.70, 0.85`
- 源目录 `SRC = _audio_ch123/out_bak_prepause`（**未注入标注的版本**）
- 也就是说 11-15 11:31 那次覆盖：`out` 里的旁白 = **只有规则常量停顿**，
  `_audio_narr_paused/`（726 条，04:32，真注入了标注）**被旁路**，没进交付。
- merge 出来的 `pause_ann.jsonl` 里 dur 是 **0.51 / 1.135 / 1.695**。这套秒数**确实被用过**——
  但只用在 `mt_final_pause.py` 的「第一优先：LLM 逐处判定」（`ll = LL.get(str(i))`）这条路上，
  产物是 `_audio_narr_paused/`（726 条，04:32）；
  而 11:31 覆盖进 `out` 的那版走的是 `_repause_v5.py`，proto 写死 `{',':0.70, '.':0.85}`。

⇒ 所以：**当前交付件 `out` 不是「LLM 投票的产物」，是「规则常量的产物」**；
含三档的那份（`_audio_narr_paused`）被旁路，没进交付。
要么把三档注进去，要么把 0.70/0.85 立为正式口径并作废三档标尺——**不能两边都留**。

### P0-3 没有驱动：闸→清单→重生成→复闸 不闭合

`regen_narr.py` 只接受 `--ids c1_0181,c3_0706`；`mk_regen_gate.py` 是**对白专用**。
旁白历史上 `out_bak_r2…r15` 十几轮全是人手递 id。
缺一个 `narr_cycle.py`：读闸表 → 出待修清单 → 调 regen → 复闸 → 写 `_narr_state.json`。

---

## 3 效果不好（都有实测数字，别再试）

### 3.1 电平口径：`ch123_rebuild.rms_voiced_db` 是假的
名字叫 rms，做的是**算术平均 dB**，与真能量平均差 **6.06dB**。
11-12 有人改用它统一口径 → 716 条全 FIX、跨度 4.0dB，已回滚。**归一只能用能量平均。**

### 3.2 重音三轴：只有时长能用
| 轴 | AUC（对 552 句 / 5989 内容词 / 745 标注重读） |
|---|---|
| **时长 rel_z** | **0.715** |
| F0 loc | 0.577 |
| 能量 rms_x | 0.568 |

三轴句内两两近零相关 ⇒ 不能加权成「一个重音分」，只能用时长当主判据。

### 3.3 EmphaClass：AUC 0.516 = 抛硬币（已弃）
716 条全跑完（本机 12 核 CPU，6.8s/条）。四种聚合（均值/最大/前3帧/帧占比）全在 0.51，帧占比 0.286（反向）。
病根：`emph_rate` 与句长 Spearman **−0.617**（<3s 报 5.20 帧/词，7s+ 报 1.97），输出退化（词级概率中位 0.000）。
**唯一保留用途**：≥5s 句 + 每词强调帧 <2 的「韵律塌陷」粗筛 → 25 条候选。

### 3.4 自然度闸：只能筛「明显不行」，不能排序
真数据 AUC：NISQA-MOS **0.49** / DIS 0.48 / COL 0.54 / SQUIM **0.76** / 组合 0.70（CI 覆盖 0.5）。
合成本 known-answer 上 0.90，真数据上全糊。⇒ 阈值 −2.3σ 只作**下限筛**，不许拿来选 take。

### 3.5 闸 6 的 z 阈值不能跨域
`Charles_nervous_1→_2` 换档后 MOS 平均 **+1.74**（21/21 全升），却仍有 19/21 按旁白 z 判 FAIL，
分项是 COL 在拖——模型把「更像真人」判成染色。对白侧只能用绝对下限（MOS ≥ 2.5）。

### 3.6 音色一致性不能句内切段测（11-14 铁律）
句内切段测声纹，同一条句子不同段之间差异大于不同 take 之间 ⇒ 判据本身无区分力。
只能整条测；段间 <0.55 报警。

### 3.7 LLM 吞吐
- `hy4`（global:hy4free）单批 **4 分钟**，63 批 ≈ **4 小时**，日间不可行
- `hy3`（global:hy3）实测 20 包可跑通（02:28 完成）
- 结论：hy4 只跑小批/夜间；主力用 hy3 + ds + mm

### 3.8 v5 峰值漏网 2 条
`_repause_v5.py` 的 rebuild 只在峰 >0.999 时归一，中间段没管：

| id | 峰值 | 限 |
|---|---|---|
| `c3_0787` | **0.920** | 0.891 |
| `c2_0498` | **0.907** | 0.891 |

物理闸不查这一项，所以它不报 FIX。

---

## 4 做不到 / 硬约束（别再花时间）

| 项 | 原因 |
|---|---|
| 云端 AI Studio 跑推理 | 容器**只有 2 核**（`nproc` 报 112 是宿主），禁装 CPU 版 torch，禁建 venv 做推理 |
| RX580 上开 Vulkan 大并发 | 8GB **必 OOM**，只能 `--threads 2 + mem_saver=true`（regen 实测用了 threads 6 勉强过） |
| 用 EmphaClass 判重音 | AUC 0.516 |
| 用 NISQA 排序/选最优 take | 真数据 AUC 0.49 |
| 用 praat 参数压倍频 | 会把真缺陷一起压掉，已否决（DECISIONS） |
| `stretch_segments` 分段伸缩 | 会破坏停顿底噪，只能 `stretch_whole` |
| 拆句生成 | N 段 = N 次表演，音色与语调都会断，禁止 |
| 停顿数字零 | 必须带底噪，零 = 数字静音，听着像掉线 |
| 逐条生成提速 | 4.9 min/条 是 RX580 上限，22 条×3 seed = 5.5 小时 |

---

## 5 命令速查

```bash
PY=G:/Python310/python.exe

# 体检
$PY G:/_setup/_chain_audit.py

# 物理闸（UTF-8 + 绝对路径，两个坑见 memory）
$env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"
$PY G:/_setup/narr_gate_phys.py --out G:/_setup/_narr_phys_now.json

# 建包 → 三路跑 → 合并
$PY G:/_setup/annotate_prosody.py build --out-dir _ann/tasks_v3 --only narr
$PY G:/_setup/_ann_llm_run.py --tasks _ann/tasks_v3 --out-root _ann/out_full/narr --lanes hy4 hy3 ds -j 2
$PY G:/_setup/annotate_prosody.py merge --dirs _ann/out_full/narr/hy4 _ann/out_full/narr/hy3 _ann/out_full/narr/ds --out-dir _ann/merged_v3 --texts <texts.jsonl>

# 标注 → 生产表 → 注入
$PY G:/_setup/pause_ann2llm.py ...
$PY G:/_setup/mt_final_pause.py --who narrator ...

# 重生成（人工点单，单条 4.9 分钟）
$PY G:/_setup/regen_narr.py --ids c1_0181,c3_0706
```

---

## 6 交付件权威指针：**缺失**

当前三份并存，谁算交付只能靠时间戳猜：

| 目录 | 条数 | 时间 | 内容 |
|---|---|---|---|
| `_audio_ch123/out` | 955（旁白 716） | 旁白为 11-15 11:31 v5 重铺 | **规则常量停顿 0.70/0.85** |
| `_audio_ch123/out_v5` | 716 | 11-15 11:28 | 与 `out` 逐条一致 |
| `_audio_narr_paused` | 726 | 11-15 04:32 | **LLM 标注停顿已注入**（未进交付） |

建议：重建后写 `_narr_state.json`（含 build_id、条数、闸表 md5、停顿口径、峰值 max），作为唯一指针。

---

## 7 2026-11-20 02:5x 链路体检（口径：标注不测，闸焊进回环，改哪环验哪环）

> 用户 02:58 纠正口径：**LLM 标注结果直接进生产，不再测标注**（三路投票/一致性已完成，不重跑）；
> 但**生成后的闸必须焊进回环**——闸报 FIX 就自动回重生成、复闸到 PASS，不是人工在旁边另点测试。
> 要砍的是「前面改一个环节、后面跑一堆无关测试」：改 rate 只验语速，改停顿只验档位，改电平只验电平。
> 已判负、不再进回环的三项：F0 双估计器复核（判负）、EmphaClass（AUC 0.516）、NISQA 排序（AUC 0.49）。

### 7.1 四段现状（实测）

| 段 | 输入 → 输出 | 现状 |
|---|---|---|
| 标注 | 716 句 → 三表 | rate **716/716**（1.00×591 / 0.84×125）｜stress **686/716**｜pause **489 句 / 1079 槽** |
| 计划 | plan.jsonl 的 rate | ❌ 仍是旧值：0.76~0.83（base 0.80），**没有一处读 rate 新表** |
| 生成 | 逐句 716 次 TTS（一 wav = 一句） | 可用，`regen_narr.py` 单条实测 294s（首次加载态）；11-15 一天跑 762 条的批次速率 ≈ 40s/条 |
| 后处理+注入 | trim → rubberband → −24dBFS → 三档停顿 | ✅ `out_paused_narr` 716 条（11-16，761 处插入）已是成品，但底子是慢 20% 的源 |
| 替换 | 覆盖 `_audio_ch123/out` 旁白位 | ❌ 无脚本、无指针、无备份约定 |

### 7.2 还差的 6 件（按阻塞顺序）

1. **~~rate 表没接生成端~~（03:0x 已接）**：新建 `_castle_en_ch123_plan_v2.jsonl`
   （narr 行 rate ← `rate_narr_sent_v1.json`：591 句 1.00 / 125 句 0.84；10 条表外句给 1.00 标 `default_1.00`；
   229 对白原样标 `dialog_untouched`）；`regen_narr.py` 新增 `--plan / --out`，dry 实测
   `c1_0017/18/23` 读到 **0.84**、`c1_0001` 读到 **1.00**。旧 `PLAN` 常量仍是 0.76~0.83，不传 `--plan` 就还是旧口径。
2. **现有 716 条不能变速救，只能重生成**：它们是 tempo 0.76~0.83 的产物（含停顿 p50 **172wpm**）；
   要回 1.00 得 tempo ≥1.20，超 [0.70,1.00] 红线且音质会掉。全量 716 次调用 ≈ **8 小时**（40s/条）。
   ⚠ 推算原速后 p50 ≈ **215wpm**（172×1.25），比有声书常见 150~170 快，这条要他知道再按 1.00 跑。
3. **stress 进不了生成**：`dots_markup.py` 只有 `rate / pitch / emo / pause`，**没有 stress/emph 词级标签**；
   历史上「标注定位 → 生成后时长检测命中」只有 **13%**。⇒ 二选一：放弃 stress（只留 pause+rate），
   或另做 pitch span 实验（`dots_markup` 已警告 rate+pause 混用会跳词，词级 span 有丢词风险）。
4. **~~替换规则缺脚本~~（03:0x 已写 `swap_narr_batch.py`）**：`out` = **955**（旁白 **726** + 对白 229）｜
   `out_paused_narr` = **716**（只旁白）。脚本按 716 名单逐文件覆盖，先备份 `_bak_swap_*`，
   收尾比对「716 全变 / 239 全不变」，任一越界即 exit 2。dry 实测：
   **wav=955，要换=716，不动=239**（不动样本 c1_0002 / c1_0005 …）。
5. **10 条旁白在链路外**：`c1_0027 c1_0049 c1_0105 c1_0167 c2_0251 c2_0267 c2_0326 c3_0797 c3_0944 c3_0953`
   （旁白句里嵌直接引语，`narr_seg=None`），三张表全无、物理闸也没照过。
6. **~~缺回环驱动~~（03:0x 已写 `narr_cycle.py`）**：读闸表 → FIX 清单 → 调 `regen_narr.py`
   （默认 `--plan v2 --out _narr_regen_1120`）→ 复闸 → 最多 3 轮 → `--apply` 时回填并备份
   `_bak_cycle_*` → 写 `_narr_state.json`。首版 state 已生成：
   PASS 712 / WATCH 4 / FIX 0、wpm p50 **172.5**、lvl 中位 **−24.2**、peak max 0.92。

### 7.3 建议的直线（闸在回环里，不在旁边另跑）

```
① plan 的 narr.rate ← rate_narr_sent_v1.json  ✅ 已生成 _castle_en_ch123_plan_v2.jsonl
② 逐句重生成 716 → _narr_regen_1120/（后台 + 看门狗，约 8h）
   regen_narr.py --ids <716> --plan _castle_en_ch123_plan_v2.jsonl --out _narr_regen_1120
③ 物理闸全量（硬切/语速/电平/削波）→ 出 FIX 清单  ✅ narr_cycle.py 已封装
   └─ FIX>0：只回 ② 重生成清单里的 id，复闸到 FIX=0；PASS/WATCH 不动
④ 三档停顿注入 → out_paused_narr2/（pause_llm_narr_v3.json + --texts，--who narrator）
   └─ 只验本环节：静音档位 0.51/1.135/1.695 命中、数字零帧=0、吞字清单
⑤ 按 716 名单覆盖 out，其余 239 条不动  ✅ swap_narr_batch.py 已封装
   └─ 只验本环节：716 条 md5 全变、239 条 md5 全不变
⑥ 写 _narr_state.json  ✅ 首版已生成（03:00）
```

### 7.4 每个环节只跑自己那一项（不做全量回归）

| 改了什么 | 只跑这一个闸 | 判据 | 不过怎么办 |
|---|---|---|---|
| rate（1.00/0.84） | 语速 + 时长 | 实测 wpm 落在计划值 ±10%；tempo ∈[0.70,1.00] | 回 ② 重生成该 id |
| 生成任一句 | 该条物理闸 + 整条声纹 | 硬切/电平/削波 PASS；声纹 ≥0.65、段间 ≥0.55 | 换 seed 重抽（≤3 次） |
| 停顿注入 | 静音档位 + 零帧 + 吞字 | 三档命中；零帧 0；吞字进清单 | 吞字的回 ② |
| 电平归一 | voiced RMS（能量平均） | −24.0dBFS ±0.5、跨度 ≤1dB、峰值 ≤0.891 | 重归一 |
| 整批替换 | 名单 md5 对比 | 716 变、239 不变 | 中止并回滚备份 |
| **不进回环** | F0 复核 / EmphaClass / NISQA 排序 | — | 已判负，别再跑 |

### 7.5 要他拍板的三件

- **A** stress 要不要注入（不注入 = 链路只用 pause + rate，stress 表只留档）
- **B** 716 条全量重生成 ≈ 8 小时、原速 p50 可能到 215wpm —— 按 1.00 跑还是保留部分慢段
- **C** 10 条引语旁白句：补标注，还是保持现状不动
