# 质检门禁 存档点（2026-10-31 17:15）

> 下次开工从这里读。**不要重跑审计**，结论都在下面和 `mt_detectors.py` 的 `valid`/`blind` 字段里。

## 一句话状态

致命项（静默失效那类）已修完并实证；阈值/估计量那类已定性为「换指标才行」，**故意不动**。
下一件事是 LLM 辅助标注，尚未开工。

## 改过的文件（指纹 = md5 前 12 位）

| 文件 | 指纹 | 行数 |
|---|---|---|
| `mt_detectors.py` | `e78050628bf3` | 693 |
| `mt_loop.py` | `ae3834883442` | 557 |
| `mt_item_qa.py` | `6f7a8940dd83` | 293 |
| `build_detector_matrix.py` | `725d8b828940` | 158 |

报告：`_detector_matrix.html`（21 条逐条带状态标签）

## 实证结果（改完重跑，非推断）

| 集合 | 结果 |
|---|---|
| 正常 120 条（`_qa_pick_ok.json`） | PASS 103 / WARN 16 / UNCHECKED 1 / **FAIL 0** |
| 退化 40 条（`_qa_deg_ok.json`） | FAIL 9 / WARN 10 / PASS 21 |

- 正常集 **零误杀**。16 条 WARN 只有两个来源：句内音色突变 10（seg_drift，warn 级不拒）+ 音高被压平 6。
- 退化集：削波 **5/5** 全拦；mono 压平 3 FAIL + 1 WARN（4/5 报出）；其余 6 类 0 FAIL，无溢出。

## 真实覆盖度（对外只认这个口径）

**登记 21 / 接入 11 / 代码生效 6 / 单条实跑 3 / 能拒收 3 / 865 条真拒 2**

- 单条实跑：`crest_clip`、`span_flatten`、`seg_drift`
- 865 条交付版上 veto 实际拒收 **2 条，全来自 span_flatten**
- 状态分布：在跑 6 / 已下线 2 / 已登记未接入 10 / 已登记未实现 3

## 修了什么（九项，都验过）

1. `import mt_detectors` 失败 → `SystemExit` 中止整轮（原来只记一句 `det_err`，日志全绿但一个检测器没跑）
2. 空壳检测器（`seg_drift`/`spk_cos`/`voice_band`/`asr_cover`）从 `PASS「仅登记」` 改 `SKIP` + 写明原因
3. `espan_flat` 标 `blocked`：band 层级修对了，但指标对等响退化**零响应**（0/5），压平后数值反而更大
4. `air_breath` 标 `blocked`：865 条 `hf` 最大 0.0327，规则要 >0.25（高 7.6 倍），且 99.4% 被 `hf<0.02` 跳过
5. `cut_drop` 改 SKIP + 写明「模型自带 ~56ms 零尾垫」——结构性不可判，不是阈值问题
6. `summarize([])` → `SKIP`（原来返回 PASS）
7. `pick_best` 全被拒 / 空列表 → **None**（原来 `or tries` 仍返回被拒那条）
8. `span_st` 的 `not m.get(...)` → `is None`（0.0 被当成「测不出」，最平那条反而跳过）
9. 判定传播改成逐条 `escalate` 声明 + `coverage()` 拆 `warn` / `warn_muted`

## 阈值侧：已判定「不改」，别再回去调

| 量 | 问题 | 处置 |
|---|---|---|
| `crest` | 原判据测的是**填充比例**（补 1s 零，削波 15.99→16.63 逃逸） | **已修**：先裁首尾静音再算，补 0→4s 零只动 0.03dB。阈值 **16.0**（削波 5/5，误杀 2/865=0.23%） |
| `span_flatten` | 类内 CV 77%、p10 是二值开关（杂帧跨 10% 时阶跃 6.17st）；AUC 0.958 但 ROC 陡起后平台 | **不动 3.0/4.5**。3.0 恰在拐点（多抓 1 条零成本）；抓全 5 条要付 15.7% 误杀 |
| `espan_flat` | 指标不对口 | 已下线 |
| `nisqa_dis` | 重测摆幅 1.58 > 两档间距 1.0；28.8% 句子 <2s 不进定级 | 未接线，别接 |

★ 汇报纪律：n=5 的召回必须带 Wilson 区间（3/5 写 60%，95%CI 23–88）；类内 CV 用 n−1 SD。

## 下次开工：LLM 辅助标注

**素材已确认存在（真实计数，不是估的）**

- 归属结果：`castle_dialog_v8.json`，1538 units
  - `CONFIRMED` **302**（金标准）/ `UNKNOWN` **618**（待判）/ `ALTERNATE` 485 / `WEAK` 112
  - 脚本：`castle_attr8.py`（状态机 + 归属动词规则，现有关键词基线）
- 情绪规则：`cloud/cuda/make_jobs.py` 的 `pick_emotion()`（侮辱词→angry、感叹号→excited、省略号→begging，**只看单句、无上下文**）

**第一步做法**

1. 从 618 块 UNKNOWN 抽 100 条
2. 让 LLM 输出结构化决策：谁说的 / 对谁说 / 有无情绪 / 强度 1–3 / 重音词 / 停顿位置
3. 用 302 条 CONFIRMED 算一致率，同时跑 `castle_attr8.py` 的规则做对照 —— 量出「强多少」而不是凭感觉

**三条不许踩回去的（实测过的）**

- LLM 输出 `<emo>` 标签 = 净负收益（ctl 85.06 > delivered 83.66 > cand 80.79）
- 「一个情节一套参数」不存在：`<pitch>` 只抬寄存器不改轮廓，`<rate>` 精度不如 rubberband
- 同句不同情绪声纹只有 **0.213** ⇒ 在 dots.tts 上「换情绪」约等于「换人」，能演的是**换 ref 档**（8 个档案）

## 产物索引

**有效**：`_qa_pick_ok.json`（正常 120）、`_qa_deg_ok.json`（退化 40）、`_cond_check.json`（865 条 7 项实测）、`_span_band_own.json`（自产起伏带）、`_detector_matrix.html`

**角色设定（2026-10-31 新增）**：`_voice_profiles.md`（原稿，权威）、`_voice_profiles.json`（镜像，含 `contrast_pairs`）、`_characters.html`（人物侧写）、`voice_lib/_chars_evidence.md`（原文证据）

**对白调节（2026-11-01 新增）**：`_dialog_tuning.md`（**七层归类 + 5 条 ref 档位映射 + 双标尺停顿表 + 20 条红线**，权威）、`_dialog_tuning.json`（机器可读镜像）、`_corpus_plan.md`（语料三条路 + 四层检索漏斗 + 三角色打法）

> **对白调节已定档（2026-11-01）**：Joseph 2 档 / Helena 2 档 / Fielding 1 档，共 **5 条 ref**（原计划 9 条，省 44%）。
> 停顿改**双标尺**：句内贴真人（0.55–0.70，找词点 1.2–1.4 占 ≤15%），句末 0.9–1.1，场景末 1.4–1.8。
> **设定里的 1.76 / 2.50 已废**（出自马修旁白母带，是对白真人中位 0.59 的 3.0–4.2 倍）。
> 三角色共 133 条台词目前**一条都生成不出来**，因为 `cast.json` 里 J/H/F 的 ref 全是 null。

**反差对（2026-10-31 晚新增，见 md §6）**
- 父子反差 Joseph（虚/长/绕）vs Edmund（实/短/冷）：**80% 在 ref 档，参数只能做节奏**
  - 关键：同一 1.7s 停顿，放句中是「犹豫」，放句末是「轻蔑」——位置比长度重要
  - `how old my father looks` **不是台词**（idx=160 的 next_narr，自由间接引语）
  - 真正的冷是三句递进：8+9 嘲讽祖父（dead old moths）→ 160 想父亲（thought）→ 80+81 继承父亲（When my father dies）——中间没有一句关心
- Helena 双面：对 Edmund 只有 2 条（1534/1535），对 Charles 30 条 ⇒ **两个 ref 档分别生成，不需要一条内切换**
  - 反证场景：1533 Edmund 威胁她儿子 → 1534 她转头抱 Edmund
  - `H_quiet` 不能靠降音量（全库 −24dBFS 抹平），要靠 HNR 高 + 句尾下坠
- **必须合并生成：全库 78 组 / 163 unit（10.6%）**，判据=同角色+相邻+前句无终止标点
  - Joseph 的「绕」本来就被切成多段 ⇒ 不合并 = 绕变结巴
　　硬阻塞：Joseph / Helena / Fielding 三个角色 **零参考音**，共约 133 句无法落地。

**已作废**（过渡态，别引用）：`_qa_wire*.json`、`_qa_fix_v3.json`、`_qa_det_test.json`（旧阈值 span WARN=6.0）、`_qa_det_v2.json`、`_qa_deg_v3~v7.json`

## 已知边界（改不了，要接受）

1. **`seg_drift` 只能告警不能拒收**。它正常旁白 FAIL 率 8%，拒收等于误杀 8% ⇒ 「同一句里某段音色没了」看得见、拦不住。这正是 LLM 要补的。
2. **`span_flatten` 召回 60%（95%CI 23–88）**，要提召回得换估计量（±2.2 倍窗 = ±13.65st，装得下 12st 八度错，名义上的「剔八度」从未生效）。
3. **`crest` 名字挂错了**：`N0755_flatamp` 被判 FAIL（14.7dB）——等响压缩压低峰值因数，方向对但报的是「削波」。
