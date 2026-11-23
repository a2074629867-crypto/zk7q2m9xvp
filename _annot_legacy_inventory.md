# 标注层遗产清单（2026-10-14 ~ 11-12 全量核查）

> 用途：**下次做标注先看这份，不要重新发明档位名。**
> 结论：10 月中下旬的版本**比我 11-12 写的完整**，而且已经过三方盲标 + Kappa 验证。
> 11-12 那版 `annotate_prosody.py` 用 `zero/short/mid/long` 是**第三套命名**，且把对白档位套到旁白上，
> 属于 skill §18.33 明写的禁区「跨体裁复用档位」。已按本文修正。

---

## 一、遗产文件全表

### 1. 规则与任务书（可直接复用）

| 文件 | 日期 | 行数 | 是什么 | 状态 |
|---|---|---|---|---|
| `DOTS_ANNOTATION_RULES.md` | 10-18 | 419 | **给 AI 标注用的精简手册**。语法、emo 9 种 type、rate 0.80/1.25、pause 不用 | ✅ 现行 |
| `DOTS_MARKUP_RULES.md` | 10-18 | 742 | 技术全档：官方常量、作废声明、改动记录 | ✅ 现行（查细节用） |
| `_annot_task.md` | 10-30 | 126 | **对白停顿标注任务书（夏尔四档）**，含判定顺序 + 4 条反例 | ✅ 现行 |
| `_matt_annot_task.md` | 10-30 | — | 旁白标注第一轮（5 档，含 drop/beat/paragraph） | ⛔ 已被第二轮取代 |
| `_matt_annot2_task.md` | 10-30 | — | **旁白标注第二轮（inner/bound/clause/para）**，明写 drop/beat 取消 | ✅ **现行，最完整** |
| `_annotated_corpora.md` | 11-01 | 93 | 带标注的公开语料库清单（Expresso/EARS/DisfluencySpeech…） | ✅ 参考 |

### 2. 已跑出的三方标注产物

| 文件 | 日期 | 规模 | 内容 |
|---|---|---|---|
| `_annot_main.json` / `_annot_hy4.json` / `_annot_ds.json` | 10-30 00:34 | 16 句对白 | **三路独立标注**：`sentence_type` + `focus`（焦点词）+ `kind[]`（每处标点） |
| `_annot_matt_main/hy4/ds.json` | 10-30 00:41 | 40 条旁白 | 第一轮 5 档（含 drop/beat） |
| `_annot2_matt_main/hy4/ds.json` | 10-30 00:47 | 60 条旁白 | **第二轮 4 档 inner/bound/clause/para**，Kappa 0.841 |
| `_ch1_pause_expect.json` | 10-30 00:57 | 78 句 | 三方合成，只判逗号 |
| `_castle_ch1_pause_expect.json` | 10-30 02:07 | 123 句 | ch1 全量停顿期望（tier + kind + d + why） |
| `_pause_cross.json` | 10-29 02:45 | 70 处 | 三方交叉：`intent`(must/opt/no) + `gap` + `pre_ratio` + `f0_st` + `acou` + `verdict` |
| `_pause_audit.json` | 10-29 01:48 | — | 停顿规则审计 |
| `_pause_llm_test.json` | 11-11 11:52 | 50 句 | 用 `lead_ann` 起的 50 句试标（`src=lead_ann`，bound 1.135） |

### 3. 重读（stress）遗产

| 文件 | 日期 | 是什么 | 结论 |
|---|---|---|---|
| `_accent_gold20.json` | 10-25 | **20 条人工金标**：声学 top1 落功能词时，是真焦点还是分析器伪影 | valid_focus 5 / ambiguous 3 / **cwt_artifact 12** |
| `_llm_accent_eval.py` + `_accent_eval_set.json` + `_accent_ctx.json` | 10-25 | LLM 判「top1 是合法重音还是伪影」，三种信号条件（bare/context/fewshot） | 脚本在，结论见 §18.17 |
| `_f0_accent.py` | 10-27 | F0 重音分析 | — |
| `_pb_stress.py` | 10-26 | prominence 计算 | — |
| `_accent_vs_labels.py` | — | 重音 vs 标签对照 | — |

### 4. 慢读（rate）遗产

| 文件 | 日期 | 是什么 | 状态 |
|---|---|---|---|
| `_narr_rate_plan_castle.json` | 11-11 10:07 | **本书 4 章全量慢读计划**，block 级 + 每段 `why` | ✅ **最完整，可直接用** |
| `_narr_rate_plan_v3.json` | 11-11 02:56 | 早期版本（paras 级） | 被 castle 版取代 |
| `_slow_ch1.json` | 10-30 12:40 | ch1 180 条降速实测（dur0/dur1/ratio/status） | ✅ 实测数据 |
| `_trim_slow.json` | 10-30 12:50 | 180 条降速后首尾裁剪量 | ✅ 实测数据 |
| `_adv_rate_exp.py` | 10-26 | **单词级 rate 标签端到端实测**（A 原文 / B 只包目标副词，同 seed 对比） | ✅ 方法论现行 |

### 5. 情绪（emo）标注

| 文件 | 日期 | 是什么 |
|---|---|---|
| `_emo_pilot.jsonl` | 11-11 16:11 | 12 条 pilot：`emo`(中文) + `type`(afraid 等) + `cond`(ctl) + `ins`(文本) + `ok` + `dur` + `sec` |
| `_emo_refs_all.json` | — | 各角色情绪参考音库（现 Charles 8 档 / Thomas 8 档） |
| `_emo_auto/candidates.json` | 11-08 | 257 条候选（Thomas 193 / Charles 64），五维 e2v 打分 |
| `refs_cast/` | 11-08 | 切好的角色情绪切片（Charles 五档各 2 条；Thomas 0） |

---

## 二、三套档位命名冲突（必须先定死）

| 用途 | **历史定案** | 我 11-12 写的 | 生产链认哪个 |
|---|---|---|---|
| **旁白** | `inner` 0.51 / `bound` 1.135 / `clause` 1.695 | `zero/short/mid/long` → 0/0.25/0.45/0.68 | ✅ **inner/bound/clause** |
| **对白** | `drop` 0 / `tight` 0.15~0.25 / `clause` 0.43~0.55 / `beat` 0.60~0.76 | 同上（错） | 透传，不校验 |
| 生产链注释 | `pause_ann2llm.py:14`：「标注用 inner/bound/clause，生产用 kind 字符串」 | — | — |

**旁白 vs 对白两套规则不可互搬**（skill §18.33 明写）：

| | 旁白 | 对白 |
|---|---|---|
| drop | **不存在**（每个标点都停，判出的 drop 实测中位 1.53s） | 存在 |
| beat | **不存在**（三方各判 0~1 条，与 para 无法区分） | 存在 |
| para | 第一轮存在，**第二轮未验证**（60 条全判 0）→ 禁用 | 不存在（62 处全 <1.5s） |
| 量级 | **0.51~1.695s** | 0~0.76s（夏尔真人上限 0.76） |
| 档数 | 3 | 4 |

---

## 三、旁白三档（定案，Kappa 0.841）

**判据（唯一有效的）**：删掉逗号后半，前半还完整吗
- 不完整（后半是必需补足）→ `inner`　median **0.51s**（n=15）
- 完整（后半是并列/状语/同位/新成分）→ `bound`　median **1.135s**（n=24）
- 句子结束 → `clause`　median **1.695s**（n=12）

**验证**：60 条三方盲标（main / Hunyuan4-preview / DS4.1F）
- 全档 Kappa **0.841**，全一致率 **85%**（第一轮 5 档只有 0.459 / 48%）
- AUC(bound>inner) = **0.840**，AUC(clause>bound) = **0.738**
- 三方各自独立判出的档位中位时长几乎相同（clause 三方都是 1.69）⇒ 结构规律，不是标注者偏差

**位置 100% 由标点决定**（母带实测）
- 逗号 218 个：96% 都停，<0.12s 只 4%
- 句号 143 个：99% 都停
- 非标点 2149 处：98% 不停（仅 33 处 ≥0.3s，是换气，文本预测不了）
⇒ 不存在「该不该停」的问题；TTS 吞逗号是缺陷，必须补插

**同档同长是对的，不许在档位内再分长短**
- 回测：三档 base MAE **0.292** / R² **0.480**；加 R3（句子进度）后 0.284 / 0.479 ⇒ **增益为零，R3 退役**
- 曾错三次：①套对白尺度（均值 0.35s）②改七档仍套对白分类 ③在 bound 内分 1.05/1.15/1.25 并用 ±0.03 找空位（纯噪声）

**spaCy 自动判档失败（63.3%）** ⇒ 文本层判档必须走 LLM

**ch1 实测**：128 个逗号需要判（句末 203 个默认 clause），main 判 bound 124 / inner 4
- 全章预算：124×1.135 + 203×1.695 ≈ **485s**，占 34%（母带 31.3%）

---

## 四、对白四档（`_annot_task.md` 10-30）

| kind | 时长 | 判据 |
|---|---|---|
| `drop` | **0** | ①语法性逗号（like/as/than/that 前后同一单元）②填充词/呼语后紧接主句（Well/Look/Anyway）③反意疑问逗号（..., will it?）④连续短项列举 |
| `tight` | **0.15~0.25** | ①插入语/补充说明（He's old, I told you.）②从句没说完 ③抢话追问紧接 |
| `clause` | **0.43~0.55** | ①两个完整分句之间 ②句号后接新句但同段对话 |
| `beat` | **0.60~0.76** | ①说完重话等对方反应 ②信息揭示/递东西 ③把话压给对方 ④转折前蓄势 |

**判定顺序不许反**：先判 drop → 再 tight → 再 beat → 剩下全 clause
**上限**：夏尔真人实测最大 **0.76s**，超过不是他的说话方式
**句末不能用 tight**

**反例（容易标错）**
- `Well, it was in somebody's house.` → `Well,` 是 drop（填充词黏主句）
- `He's old, I told you.` → `old,` 是 tight（I told you 是插入语）
- `It is my house, it is private.` → `house,` 是 clause（两个完整分句 + 宣示）
- `Downstairs is something very valuable. Something you've never seen.` → 句号是 beat

**16 条三方标注 Kappa 只有 0.61**，分歧全在 tight/beat ⇒ skill 标注「对白规则冻结未确认」

**`_annot_main/hy4/ds.json` 还带两个字段**（我 11-12 版丢了）：
- `sentence_type`：stmt / wh / yesno / tag / echo（**wh 优先**，`Oh, what is it?` 不是反意疑问）
- `focus`：这一条台词最想让对方听见的那一个词（指责点/否认点/炫耀点），原词照抄

---

## 五、重读：文本标注改不了音高重音（重要否决）

**N0710「quietly 该重读」实测（10-22）**：

| 写法 | quietly F0 | quietly 后停顿 |
|---|---|---|
| 原文 | −0.96 半音 | 0.256s |
| `walked back, quietly,` | **−1.66**（更低） | 0.800s（过长） |
| `walked back — quietly —` | **−2.86**（更低） | 0.304s |
| `…back quietly. To his…` | −0.37 | 0.160s |

⇒ **四种文本标注全部无效，只改停顿，改不了音高重音。**

**真因 = 句子长度（决定性）**

| 输入 | 词数 | quietly F0 | 强度 |
|---|---|---|---|
| `And walked back quietly,` | 4 | **+1.87 半音** | **全句峰值** ✅ |
| `walked back quietly to his own bedroom` | 7 | +0.74 | 全句峰值 ✅ |
| 原句 | 18 | −0.96 | −2.0 dB ❌ |

⇒ **模型在 ≤7 词内能把 nucleus 放对，≥14 词抹平。**
本书 >14 词：ch1 77 / ch2 74 / ch3 153 = **304 条（35%）**，95% 句内带逗号（可自然拆）。

**重读是两种正交形态**（18.17，真人 160 句 / 930 词）
- `rel`（词长 ÷ 句中位）：普通 1.00 / 句内最长词 **1.71**
- `loc`（半音）：普通 +0.81 / 句内最高 **+2.71**
- 拖长的词音高普通，抬高的词时长普通 ⇒ **两条独立通道**
- 我们只做了 loc（交付版分位 86），rel 分位只有 **59**

**词级重音的唯一手段**：`<rate, factor=0.75>` 包那个词（+33% 时长）；**禁用 `<pitch>`**
**验收用绝对水位**：`REL_OK=1.40`（对照 p95 上留一格）/ `FULL_GAIN_MAX=1.15`（整句不得超对照 15%）
**命中率只有 13%，每条约需 7~8 个 seed** ⇒ 降级为「顺带捡」，不是主路径

**`_accent_gold20` 的警告**：声学 top1 落功能词时，20 条里 **12 条是 CWT 分析器伪影**（句首 F0 重置/紧邻停顿边界效应），只有 5 条是真焦点
⇒ **不能拿声学 top1 直接当「该重读」的金标**

---

## 六、慢读：block 级，不是句子级

**`_narr_rate_plan_castle.json` 的 `_meta`（现成硬约束，直接用）**
```
base_rate 0.80，range [0.72, 0.84]，只降不升
rate 越低语速越慢；0.72 是实测硬下限（0.70 会丢整句）
硬约束：相邻段差 ≤0.06、减速词数 ≤20%、rate≤0.72 最多 1 段
单位：chunk block（target 120 词 / hard_max 165），不是句子
```

**已有产物**：本书 4 章全量，每 block 带 `rate` + 中文 `why`
例：`B000 rate=0.78 why=开场起手：三个月前祖母死了，然后搬进这所房子。要像坐下来开口讲故事那样起，比正文慢半拍，句尾不要收得太干净`

**技术细节**
- 减速必须按 `1/rate` 放宽 `max_tokens`，否则长块截断
- `_slow_ch1.json` 180 条实测：ratio 1.1111（即 rate 0.90 档）；`_trim_slow.json` 给降速后首尾裁剪量

**⚠ 我 11-12 版 `rate_llm.json` 写成「句子级 + rate ∈ [0.72,0.84]」** —— 范围对，**单位错**（应是 block 级 120 词）

---

## 七、我 11-12 那版的 5 处错（已修正）

| # | 错在哪 | 正确 | 依据 |
|---|---|---|---|
| 1 | 旁白用 `zero/short/mid/long` | `inner/bound/clause` | §18.34，Kappa 0.841 |
| 2 | 旁白秒数 0/0.25/0.45/0.68 | 0.51/1.135/1.695（长 2~3 倍） | §18.34 三方中位 |
| 3 | REQUIREMENTS 32.2 写「同一句里每个停顿不一样长」 | **对白如此，旁白必须同档同长** | §18.34 回测 R3 增益为零 |
| 4 | 32.2 写「重点副词 → 重读」当成能靠标注做到 | 标注只能**定位**该重读的词；**能不能读到要靠生成后检测 + 抽 seed**（命中 13%） | N0710 + §18.17 |
| 5 | `rate_llm` 定为句子级 | **block 级**（120 词） | `_narr_rate_plan_castle.json` |

---

## 八、正确的接线方式（下次照这个做）

```
① 旁白停顿
   _pause_ctx.jsonl（1085 边界，含左右 7 词 + 整段）
   → 3 路独立标注（只给 inner/bound/clause，不给秒数）
   → 秒数由档位 median 直接映射（0.51 / 1.135 / 1.695），**不许档内再分**
   → pause_ann2llm.py → pause_llm_castle.json → mt_final_pause.py

② 对白停顿
   → 4 路（drop/tight/clause/beat，判定顺序不许反，句末禁 tight）
   → 档位 → 秒数（0 / 0.20 / 0.49 / 0.68），上限 0.76
   → 同上进生产链

③ 慢读
   _narr_blocks.json（120 词/块）→ 3 路标 rate + why
   → 校验硬约束（相邻差≤0.06、减速≤20%、0.72 最多 1 段）
   → 进 gen（按 1/rate 放宽 max_tokens）

④ 重读（**不要当成能靠标注做到**）
   → LLM 只标「哪几个词是焦点」（复用 _annot_*.json 的 focus 字段）
   → 生成后检测 rel（REL_OK=1.40）+ 整句增益（FULL_GAIN_MAX=1.15）
   → 没读到就抽 seed，最多 7~8 个；仍不行才 `<rate, factor=0.75>` 包那个词
```

---

## 九、还没被用起来的遗产（可直接捡）

| 遗产 | 为什么值钱 | 怎么用 |
|---|---|---|
| `_annot_*.json` 的 `sentence_type` + `focus` | 我 11-12 版完全没有这两个字段 | 并进 `stress_llm`：`focus` 就是该重读的词，`sentence_type` 决定句末停顿档 |
| `_pause_cross.json` 的 `intent`(must/opt/no) | 三档意图标注，70 处 | 可作 `pause_llm` 的交叉校验 |
| `_accent_gold20.json` | 人工金标，专门抓「声学 top1 是伪影」 | 验收重读检测器，不是验收生成 |
| `_adv_rate_exp.py` | 单词级 rate 标签的 A/B 实测框架 | 以后测「副词慢读到底有没有效」直接用 |
| `_narr_rate_plan_castle.json` | 4 章全量 + why | **慢读层其实已经做完了**，只是没接进 gen |
| `DOTS_ANNOTATION_RULES.md` | 官方 1152 例 + 40 组实测的浓缩 | 打标签前必读，写错 = 静默失效 |
| `_annotated_corpora.md` | 12 个带标注的公开库 | 缺素材时（如 Thomas defiant）可换源 |
