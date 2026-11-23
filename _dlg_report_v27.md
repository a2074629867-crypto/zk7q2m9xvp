# 对白链路交付报告

数据源：`_gate_dlg_v27.json`（239 条）

## 一、分层（互斥，共 239 条）

| 类 | 含义 | 条数 | 占全量 |
|---|---|---|---|
| A | 通过（声学+声纹+情绪全过） | 124 | 51.9% |
| B | 待重生成（真缺陷） | 1 | 0.4% |
| G | 音色一致性异常（句内突变/换人/档内离群，第 4+5 闸） | 10 | 4.2% |
| H | 自然度不达标（NISQA+SQUIM 下限筛，第 6 闸） | 3 | 1.3% |
| C | 素材不可用（缺档 / 参考片段质量不达标，需换素材） | 8 | 3.3% |
| D | 短句未验收（声学指标不成立） | 54 | 22.6% |
| E | 情绪边缘 / 生成层不可达（p10~p25、撞数学顶、结构性推不动） | 39 | 16.3% |
| F | 待人工 | 0 | 0.0% |

**严格通过：124 条（51.9%）**

**可听（含边缘需人耳）：163 条（68.2%）** —— A 124 + E 39

**需要动音频：22 条** —— B 待重生成 1 + G 音色一致性 10 + H 自然度 3 + C 缺档 8

**测不了（不是坏）：54 条** —— D 短句 54 + F 待人工 0

### D 短句按词数

| 词数 | 条数 |
|---|---|
| 1 | 21 |
| 2 | 7 |
| 3 | 8 |
| 4+ | 18 |

> 1-3 词条目上，声纹 embedding 与 F0 统计不成立（0.5s 不足以刻画说话人）。这类**不能判 PASS，也不能算坏**，交付时单列。

### C 缺档明细（素材缺口）

| 角色 | 情绪 | 条数 | 可解性 |
|---|---|---|---|
| Charles | 紧张 | 3 | 档已补齐，重跑可解 |
| Thomas | 委屈 | 1 | 档已补齐，重跑可解 |
| Thomas | 激动反抗 | 1 | 档已补齐，重跑可解 |
| Thomas | 警惕 | 1 | 档已补齐，重跑可解 |
| Joseph | 激动反抗 | 1 | 档已补齐，重跑可解 |
| Thomas | 兴奋 | 1 | 档已补齐，重跑可解 |

> 详见 `_missing_refs_report.md`。「素材仍缺」= TTS 重跑变不出来；「档已补齐」= 重跑就能解决，只是还没重跑。

### B 待重生成明细

| id | 角色 | 原因 | 文本 |
|---|---|---|---|
| `c2_0487` | Charles | emo_low | ‘What are you going back into the house for? |

### 音色一致性异常（第 4+5 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0149` | Joseph | intra_drift | ‘It’s easy for you to despise and shrug  |
| `c2_0291` | Charles | scs_outlier | ‘Well, my mother can’t afford to buy us  |
| `c2_0321` | Charles | intra_drift, scs_outlier | ‘I told you. When he was in the Battle o |
| `c2_0326` | Thomas | intra_drift | Hooper raised his eyebrows, ‘I should th |
| `c2_0371` | Thomas | intra_switch, ref_fallback | ‘Only schools for poor people. Boarding  |
| `c2_0437` | Thomas | emo_marginal, intra_drift, ref_poor | ‘Oh. Are they going to stay, then?’ |
| `c2_0471` | Charles | scs_outlier | ‘They do fall. They fall on their own.’ |
| `c3_0625` | Charles | intra_drift, role_unmeasurable, scs_outlier | ‘There isn’t any key.’ |
| `c3_0834` | Thomas | intra_drift | ‘Go on then,’ he said in a soft voice, ‘ |
| `c3_0840` | Thomas | intra_drift | ‘My grandfather. Haven’t you ever heard  |

### 自然度不达标（第 6 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0046` | Joseph | nat_fail | ‘Yes.’ |
| `c2_0306` | Thomas | emo_marginal, nat_fail, role_unmeasurable | ‘It was years ago, dozens of years. It w |
| `c3_0838` | Thomas | emo_unreachable, nat_fail | ‘Yes, every sort of moth in the world.’ |

### E 情绪边缘明细

| id | 角色 | 情绪 | 值 | tier |
|---|---|---|---|---|
| `c1_0005` | Joseph | 紧张 | 0.170 | 未达 |
| `c1_0013` | Joseph | 紧张 | 0.208 | 未达 |
| `c1_0015` | Joseph | 紧张 | 0.228 | 未达 |
| `c1_0035` | Joseph | 紧张 | 0.204 | 未达 |
| `c1_0043` | Joseph | 紧张 | 0.245 | 未达 |
| `c1_0047` | Joseph | 紧张 | 0.224 | 未达 |
| `c1_0049` | Joseph | 紧张 | 0.232 | 未达 |
| `c1_0163` | Joseph | 紧张 | 0.226 | 未达 |
| `c1_0165` | Joseph | 紧张 | 0.232 | 未达 |
| `c2_0210` | Thomas | 警惕 | 0.002 | 勉强 |
| `c2_0246` | Charles | 紧张 | 0.196 | 未达 |
| `c2_0264` | Thomas | 兴奋 | 0.193 | 未达 |
| `c2_0268` | Charles | 警惕 | 0.003 | 勉强 |
| `c2_0298` | Thomas | 警惕 | 0.002 | 勉强 |
| `c2_0299` | Charles | 紧张 | 0.230 | 未达 |
| `c2_0312` | Charles | 紧张 | 0.247 | 未达 |
| `c2_0314` | Charles | 紧张 | 0.262 | 勉强 |
| `c2_0327` | Charles | 紧张 | 0.251 | 未达 |
| `c2_0328` | Thomas | 警惕 | 0.001 | 勉强 |
| `c2_0358` | Charles | 激动反抗 | 0.615 | 勉强 |
| `c2_0413` | Joseph | 激动反抗 | 0.545 | 勉强 |
| `c2_0419` | Joseph | 紧张 | 0.223 | 未达 |
| `c2_0428` | Joseph | 激动反抗 | 0.607 | 勉强 |
| `c2_0469` | Charles | 委屈 | 0.464 | 勉强 |
| `c2_0480` | Helena | 兴奋 | 0.295 | 勉强 |
| `c2_0491` | Thomas | 兴奋 | 0.267 | 勉强 |
| `c3_0649` | Charles | 警惕 | 0.003 | 勉强 |
| `c3_0802` | Joseph | 兴奋 | 0.354 | 勉强 |
| `c3_0803` | Joseph | 兴奋 | 0.175 | 未达 |
| `c3_0814` | Charles | 警惕 | 0.003 | 勉强 |
| `c3_0839` | Charles | 紧张 | 0.240 | 未达 |
| `c3_0861` | Charles | 紧张 | 0.263 | 勉强 |
| `c3_0874` | Charles | 紧张 | 0.261 | 勉强 |
| `c3_0876` | Charles | 紧张 | 0.227 | 未达 |
| `c3_0922` | Charles | 紧张 | 0.246 | 未达 |
| `c3_0942` | Helena | 兴奋 | 0.113 | 未达 |
| `c3_0943` | Helena | 紧张 | 0.231 | 未达 |
| `c3_0944` | Helena | 紧张 | 0.269 | 勉强 |
| `c3_0953` | Charles | 兴奋 | 0.264 | 勉强 |

## 二、电平与峰值

- **voiced RMS**（去静音后能量平均，归一指标）中位 -24.00 dBFS，区间 -24.27 ~ -23.96（跨度 0.31 dB）
- 结论：**已达标**（需求 23 要求 ≤1dB）
- 全段 RMS 中位 -24.7 dBFS，区间 -27.3 ~ -24.0（跨度 3.3 dB）—— 含停顿时长，非归一指标，仅供时长/停顿参考
- 峰值最大 0.726，削波 0 条

## 三、本轮变化（对比 `_gate_dlg_v26.json`）

| 类 | 上一版 | 本版 | 变化 |
|---|---|---|---|
| A | 116 | 124 | +8 |
| B | 1 | 1 | +0 |
| G | 10 | 10 | +0 |
| H | 3 | 3 | +0 |
| C | 7 | 8 | +1 |
| D | 57 | 54 | -3 |
| E | 45 | 39 | -6 |
| F | 0 | 0 | +0 |

- **A** 新进 9 ['c2_0195', 'c2_0230', 'c2_0251', 'c2_0308', 'c2_0313', 'c3_0622', 'c3_0651', 'c3_0826', 'c3_0856'] ｜ 移出 1 ['c2_0257']
- **C** 新进 1 ['c3_0921'] ｜ 移出 0 
- **E** 新进 0  ｜ 移出 6 ['c2_0195', 'c2_0230', 'c2_0308', 'c3_0651', 'c3_0826', 'c3_0921']
