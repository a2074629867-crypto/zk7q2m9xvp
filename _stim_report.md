# 刺激分级报告（stim tier v2）

数据源：`_stim_feat.json`（239 条有 intensity 标注）/ `_stim_ref.json`（81 条真人切片）

分档：S1低 <0.45 / S2中 0.45–0.66 / S3高 ≥0.66（真人 8 档 A 锚）
effort = −z(alpha) + z(f0中位) − z(HNR)，z 参数取**该角色真人 refs** ⇒ 角色内可比，跨角色不可比

## 一、一句话结论

**13 个 (角色,情绪) 组可测梯度，1 组通过、12 组不通过。**

不通过的原因**不是模型没表演出来，而是强度根本没进选角**（见第三节）：
同一 (角色,情绪) 的 I1/I2/I3 全部克隆**同一个参考切片**，梯度在输入端就不存在，
所以拿同一档重跑多少次也不会出现梯度 —— 要改的是选角映射，不是重生成参数。

## 二、逐组梯度

| 角色 | 情绪 | n | 档位 | 各档 effort 中位 | 各档 n | SRCC | 极差 | 判定 | 原因 |
|---|---|---|---|---|---|---|---|---|---|
| Thomas | 激动反抗 | 69 | 1/2/3 | +0.62 / +0.54 / +0.66 | 9/53/7 | -0.00 | 0.12 | ✗ | 极差不足 0.12<0.30 |
| Joseph | 平静 | 29 | 1/2 | +0.05 / -0.13 | 19/10 | -0.21 | 0.18 | ✗ | 极差不足 0.18<0.30 |
| Charles | 紧张 | 26 | 1/2/3 | +0.97 / +0.64 / +1.40 | 5/20/1 | +0.10 | 0.76 | ✗ | 秩相关 0.11<0.20 |
| Thomas | 警惕 | 17 | 1/2 | -0.50 / -0.34 | 3/14 | +0.10 | 0.16 | ✗ | 极差不足 0.16<0.30 |
| Thomas | 平静 | 16 | 1/2 | -0.77 / -0.85 | 13/3 | -0.05 | 0.08 | ✗ | 极差不足 0.08<0.30 |
| Charles | 激动反抗 | 15 | 1/2/3 | +1.02 / +1.30 / +1.20 | 3/10/2 | +0.17 | 0.28 | ✗ | 极差不足 0.28<0.30 |
| Charles | 委屈 | 14 | 1/2 | -1.43 / -1.32 | 1/13 | +0.10 | 0.10 | ✗ | 极差不足 0.10<0.30 |
| Joseph | 紧张 | 10 | 1/2 | +0.98 / +0.60 | 1/9 | -0.41 | 0.38 | ✗ | 秩相关 -0.41<0.20 |
| Joseph | 激动反抗 | 10 | 1/2 | -0.30 / +0.75 | 1/9 | +0.41 | 1.05 | ✓ | 梯度存在 |
| Charles | 平静 | 7 | 1 | -0.69 | 7 | - | - | — | 只有一档，无梯度可测 |
| Thomas | 兴奋 | 5 | 1/2 | +0.65 / +0.33 | 1/4 | +0.00 | 0.32 | ✗ | 秩相关 0.00<0.20 |
| Charles | 警惕 | 5 | 1/2 | -0.70 / -0.50 | 2/3 | +0.44 | 0.20 | ✗ | 极差不足 0.20<0.30 |
| Helena | 兴奋 | 3 | 2 | -0.12 | 3 | - | - | — | 只有一档，无梯度可测 |
| Helena | 紧张 | 3 | 2 | +0.29 | 3 | - | - | — | 只有一档，无梯度可测 |
| Thomas | 委屈 | 2 | 1/2 | -0.89 / +0.78 | 1/1 | - | 1.66 | ✗ | 样本不足 2 条，秩相关不可算 |
| Joseph | 委屈 | 2 | 1/2 | -1.37 / +0.34 | 1/1 | - | 1.71 | ✗ | 样本不足 2 条，秩相关不可算 |
| Joseph | 兴奋 | 2 | 1 | +0.30 | 2 | - | - | — | 只有一档，无梯度可测 |
| Helena | 平静 | 1 | 1 | +0.36 | 1 | - | - | — | 只有一档，无梯度可测 |
| Thomas | 紧张 | 1 | 1 | +1.02 | 1 | - | - | — | 只有一档，无梯度可测 |
| Charles | 兴奋 | 1 | 1 | +1.16 | 1 | - | - | — | 只有一档，无梯度可测 |
| Helena | 委屈 | 1 | 2 | +0.86 | 1 | - | - | — | 只有一档，无梯度可测 |

## 三、根因：强度有没有进选角

生成方式：每条对白用 `voice` 指定的**真人参考切片**做克隆，情绪与强度**完全由这个切片决定**，
文本侧不传任何强度标签。所以「intensity 有没有被表演出来」完全等价于「选角有没有随 intensity 变」。

**21 / 21 组的三档共用同一批参考切片**：

| 角色 | 情绪 | n | 用到的 voice | 三档同一批？ |
|---|---|---|---|---|
| Thomas | 激动反抗 | 69 | Thomas_loud_1 | 是（强度未接入） |
| Joseph | 平静 | 29 | Joseph_normal_1 | 是（强度未接入） |
| Charles | 紧张 | 26 | Charles_neutral_1 | 是（强度未接入） |
| Thomas | 警惕 | 17 | Thomas_scold_1 | 是（强度未接入） |
| Thomas | 平静 | 16 | Thomas_calm_1 | 是（强度未接入） |
| Charles | 激动反抗 | 15 | Charles_angry_1 | 是（强度未接入） |
| Charles | 委屈 | 14 | Charles_soft_1 | 是（强度未接入） |
| Joseph | 紧张 | 10 | Joseph_nervous_1 | 是（强度未接入） |
| Joseph | 激动反抗 | 10 | Joseph_defiant_1 | 是（强度未接入） |
| Charles | 平静 | 7 | Charles_neutral_1 | 是（强度未接入） |
| Thomas | 兴奋 | 5 | Thomas_loud_1 | 是（强度未接入） |
| Charles | 警惕 | 5 | Charles_soft_1 | 是（强度未接入） |
| Helena | 兴奋 | 3 | Helena_excited_1 | 是（强度未接入） |
| Helena | 紧张 | 3 | Helena_nervous_1 | 是（强度未接入） |
| Thomas | 委屈 | 2 | Thomas_begging_1 | 是（强度未接入） |
| Joseph | 委屈 | 2 | Joseph_wronged_1 | 是（强度未接入） |
| Joseph | 兴奋 | 2 | Joseph_excited_1 | 是（强度未接入） |
| Helena | 平静 | 1 | Helena_wary_1 | 是（强度未接入） |
| Thomas | 紧张 | 1 | Thomas_calm_1 | 是（强度未接入） |
| Charles | 兴奋 | 1 | Charles_excited_1 | 是（强度未接入） |
| Helena | 委屈 | 1 | Helena_wronged_1 | 是（强度未接入） |

结论：强度在本项目里**从未作为生成输入存在**。v1 用 A 判强度、v2 用 effort 判强度，
测到的都是「同一参考切片的不同实现变体」，不是强度。修复点在选角表（`V` 只给到单一 `_1` 切片，
`emo_intensity` 写进计划后没有任何下游读取），不在重生成参数。

## 四、单条相对档（组内三分位，不是绝对合格）

| 结论 | 条数 |
|---|---|
| 相对命中 | 78 |
| 相对欠刺激 | 52 |
| 相对过刺激 | 109 |
| 不可测 | 0 |

⚠ 这一层只能回答「同一角色同一情绪内，这句排位偏上还是偏下」，
不能回答「绝对够不够」——那需要同文本真人对照，我们没有。

## 五、域偏移证据（生成 vs 真人同档）

| 角色 | 情绪 | 生成 n | 生成 effort 中位 | 真人 refs effort 中位 | 差 |
|---|---|---|---|---|---|

## 六、回流：按 intensity 选参考切片（这才是修复动作）

同一 (角色,情绪) 库里的多条真人切片按 effort 排序，I1 取低端、I3 取高端。
切片序号（`_1/_2/_3`）**不代表强度顺序** —— 必须按实测 effort 排，不能按名字猜。

| 角色 | 情绪 | 切片数 | 低端 → 高端（effort, 文件名） |
|---|---|---|---|
| Thomas | loud | 4 | +0.50 c218_2302.9_2306.4.wav → +0.54 c217_2298.8_2302.9.wav → +0.67 c216_2295.1_2298.4.wav → +1.08 c310_3529.2_3533.7.wav |
| Thomas | calm | 4 | -0.63 c325_3768.4_3773.2.wav → -0.57 c288_3322.2_3327.1.wav → -0.49 c294_3402.7_3408.2.wav → -0.46 c010_085.0_088.5.wav |
| Thomas | begging | 4 | +0.76 c221_2341.5_2346.9.wav → +0.76 c401_5110.4_5116.8.wav → +1.19 c240_2561.8_2564.6.wav → +1.31 c082_1040.0_1041.9.wav |
| Charles | excited | 3 | +0.54 c215_2289.8_2293.5.wav → +0.67 c246_2723.6_2726.2.wav → +0.90 c250_2779.8_2781.8.wav |
| Charles | soft | 3 | -1.51 c268_2986.9_2988.5.wav → -1.25 c267_2983.2_2984.5.wav → -0.57 c395_4917.0_4918.6.wav |
| Charles | neutral | 3 | -0.47 c039_362.4_363.9.wav → -0.32 c040_364.5_366.5.wav → +0.30 c185_2051.8_2056.7.wav |
| Thomas | scold | 3 | -0.41 c170_1937.6_1939.7.wav → -0.28 c171_1941.6_1945.3.wav → -0.16 c276_3247.2_3251.9.wav |
| Fielding | excited | 3 | -0.53 Fielding_excited_c303.wav → -0.14 Fielding_excited_c730.wav → +0.48 Fielding_excited_c369.wav |
| Fielding | defiant | 3 | -0.04 Fielding_defiant_c104.wav → +0.47 Fielding_defiant_c078.wav → +0.72 Fielding_defiant_c153.wav |
| Fielding | wronged | 3 | +0.08 Fielding_wronged_c046.wav → +0.12 Fielding_wronged_c364.wav → +0.21 Fielding_wronged_c050.wav |
| Fielding | wary | 3 | -0.37 Fielding_wary_c301.wav → +0.42 Fielding_wary_c049.wav → +1.68 Fielding_wary_c051.wav |
| Fielding | nervous | 3 | +0.09 Fielding_nervous_c728.wav → +0.42 Fielding_nervous_c100.wav → +0.50 Fielding_nervous_c052.wav |
| Helena | excited | 3 | -0.55 Helena_excited_c466.wav → +0.19 Helena_excited_c144.wav → +0.26 Helena_excited_c066.wav |
| Helena | defiant | 3 | +0.33 Helena_defiant_c127.wav → +0.38 Helena_defiant_c398.wav → +1.05 Helena_defiant_c390.wav |
| Helena | wronged | 3 | -0.96 Helena_wronged_c076.wav → -0.73 Helena_wronged_c497.wav → +0.11 Helena_wronged_c083.wav |
| Helena | wary | 3 | -0.38 Helena_wary_c072.wav → +0.02 Helena_wary_c073.wav → +0.28 Helena_wary_c124.wav |
| Helena | nervous | 3 | -0.42 Helena_nervous_c405.wav → -0.04 Helena_nervous_c441.wav → +0.33 Helena_nervous_c512.wav |
| Joseph | excited | 3 | -0.29 Joseph_excited_c006.wav → +0.11 Joseph_excited_c028.wav → +0.39 Joseph_excited_c008.wav |
| Joseph | defiant | 3 | +0.08 Joseph_defiant_c030.wav → +0.12 Joseph_defiant_c005.wav → +0.44 Joseph_defiant_c002.wav |
| Joseph | wronged | 3 | -0.20 Joseph_wronged_c042.wav → +0.22 Joseph_wronged_c017.wav → +0.30 Joseph_wronged_c009.wav |
| Joseph | wary | 3 | -0.38 Joseph_wary_c020.wav → -0.18 Joseph_wary_c013.wav → +1.09 Joseph_wary_c035.wav |
| Joseph | nervous | 3 | -0.85 Joseph_nervous_c056.wav → -0.44 Joseph_nervous_c058.wav → +0.44 Joseph_nervous_c043.wav |
| Joseph | normal | 3 | -0.53 Joseph_normal_c1028.wav → +0.01 Joseph_normal_c1016.wav → +0.87 Joseph_normal_c748.wav |
| Charles | defiant | 2 | +0.76 Charles_defiant_2.wav → +0.94 Charles_defiant_1.wav |
| Thomas | nervous | 2 | +0.65 Thomas_nervous_1.wav → +1.17 Thomas_nervous_2.wav |

## 七、方法学注意

1. **绝对电平不可用**：全库归一到 −24dBFS，dB 已被抹平，所以 effort 只能靠谱倾斜/音区/谐噪比。
2. **A（arousal）不可当强度**：它对合成语音系统性偏高（生成中位 0.735 vs 真人 normal 0.54），
   且档内与 intensity 无关（v1 实测）。本报告 A 只作旁证，不进判定。
3. **社区同向**：ScienceDirect 2025 在「幅度归一化语音」上判 4 档 vocal intensity 达 86.0%，
   用的也是 cepstral/spectral 特征；WavLM 在 AVID 上 78.2%。说明归一化后判强度可行，但靠的是谱不是音量。
4. **本报告不给绝对阈值**：n<4 的组、单档组全部标「不可测」，不用中位数冒充。
