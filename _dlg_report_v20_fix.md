# 对白链路交付报告

数据源：`_gate_dlg_v20.json`（239 条）

## 一、分层（互斥，共 239 条）

| 类 | 含义 | 条数 | 占全量 |
|---|---|---|---|
| A | 通过（声学+声纹+情绪全过） | 85 | 35.6% |
| B | 待重生成（真缺陷） | 2 | 0.8% |
| G | 音色一致性异常（句内突变/换人/档内离群，第 4+5 闸） | 17 | 7.1% |
| H | 自然度不达标（NISQA+SQUIM 下限筛，第 6 闸） | 2 | 0.8% |
| C | 素材不可用（缺档 / 参考片段质量不达标，需换素材） | 28 | 11.7% |
| D | 短句未验收（声学指标不成立） | 76 | 31.8% |
| E | 情绪边缘 / 生成层不可达（p10~p25、撞数学顶、结构性推不动） | 28 | 11.7% |
| F | 待人工 | 1 | 0.4% |

**严格通过：85 条（35.6%）**

**可听（含边缘需人耳）：113 条（47.3%）** —— A 85 + E 28

**需要动音频：49 条** —— B 待重生成 2 + G 音色一致性 17 + H 自然度 2 + C 缺档 28

**测不了（不是坏）：77 条** —— D 短句 76 + F 待人工 1

### D 短句按词数

| 词数 | 条数 |
|---|---|
| 1 | 21 |
| 2 | 11 |
| 3 | 11 |
| 4+ | 33 |

> 1-3 词条目上，声纹 embedding 与 F0 统计不成立（0.5s 不足以刻画说话人）。这类**不能判 PASS，也不能算坏**，交付时单列。

### C 缺档明细（素材缺口）

| 角色 | 情绪 | 条数 |
|---|---|---|
| Thomas | 警惕 | 12 |
| Thomas | 兴奋 | 4 |
| Thomas | 激动反抗 | 3 |
| Charles | 激动反抗 | 3 |
| Joseph | 激动反抗 | 2 |
| Joseph | 紧张 | 1 |
| Thomas | 委屈 | 1 |
| Helena | 平静 | 1 |
| Helena | 委屈 | 1 |

> 详见 `_missing_refs_report.md`。**TTS 重跑变不出这些档。**

### B 待重生成明细

| id | 角色 | 原因 | 文本 |
|---|---|---|---|
| `c2_0306` | Thomas | intra_switch, mostly_silence, nat_fail, ref_fallback, scs_outlier | ‘It was years ago, dozens of years. It was h |
| `c2_0487` | Charles | emo_low | ‘What are you going back into the house for? |

### 音色一致性异常（第 4+5 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0149` | Joseph | intra_drift | ‘It’s easy for you to despise and shrug  |
| `c2_0217` | Thomas | intra_switch, ref_fallback, role_unmeasurable | ‘It is my house,’ he thought, ‘it is pri |
| `c2_0271` | Thomas | intra_switch, ref_fallback | ‘My grandfather died in this room. Not v |
| `c2_0291` | Charles | scs_outlier | ‘Well, my mother can’t afford to buy us  |
| `c2_0321` | Charles | intra_drift | ‘I told you. When he was in the Battle o |
| `c2_0326` | Thomas | intra_drift, ref_fallback | Hooper raised his eyebrows, ‘I should th |
| `c2_0356` | Charles | scs_outlier | ‘I’m supposed to, that’s what your fathe |
| `c2_0368` | Charles | intra_switch | ‘I think... I don’t know. I think it’s f |
| `c2_0371` | Thomas | intra_switch, ref_fallback | ‘Only schools for poor people. Boarding  |
| `c2_0372` | Charles | scs_outlier | ‘It’s... I don’t know. I daresay my fath |
| `c2_0437` | Thomas | emo_marginal, intra_drift, ref_poor | ‘Oh. Are they going to stay, then?’ |
| `c2_0471` | Charles | scs_outlier | ‘They do fall. They fall on their own.’ |
| `c3_0625` | Charles | intra_drift, scs_outlier | ‘There isn’t any key.’ |
| `c3_0834` | Thomas | intra_drift, ref_fallback | ‘Go on then,’ he said in a soft voice, ‘ |
| `c3_0840` | Thomas | intra_severe, ref_fallback | ‘My grandfather. Haven’t you ever heard  |
| `c3_0922` | Charles | hard_cap, intra_switch | ‘It’s O.K. I just got locked in. Goodnig |
| `c3_0953` | Charles | emo_marginal, intra_switch, scs_outlier | He wrote home, ‘I like it here very much |

### 自然度不达标（第 6 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0046` | Joseph | nat_fail | ‘Yes.’ |
| `c3_0838` | Thomas | nat_fail, ref_fallback | ‘Yes, every sort of moth in the world.’ |

### E 情绪边缘明细

| id | 角色 | 情绪 | 值 | tier |
|---|---|---|---|---|
| `c1_0005` | Joseph | 紧张 | 0.221 | 未达 |
| `c1_0015` | Joseph | 紧张 | 0.228 | 未达 |
| `c1_0035` | Joseph | 紧张 | 0.244 | 未达 |
| `c1_0043` | Joseph | 紧张 | 0.231 | 未达 |
| `c1_0047` | Joseph | 紧张 | 0.224 | 未达 |
| `c1_0049` | Joseph | 紧张 | 0.256 | 勉强 |
| `c1_0163` | Joseph | 紧张 | 0.227 | 未达 |
| `c1_0165` | Joseph | 紧张 | 0.239 | 未达 |
| `c2_0195` | Helena | 兴奋 | 0.261 | 勉强 |
| `c2_0230` | Joseph | 激动反抗 | 0.600 | 勉强 |
| `c2_0246` | Charles | 紧张 | 0.205 | 未达 |
| `c2_0299` | Charles | 紧张 | 0.222 | 未达 |
| `c2_0312` | Charles | 紧张 | 0.247 | 未达 |
| `c2_0314` | Charles | 紧张 | 0.262 | 勉强 |
| `c2_0327` | Charles | 紧张 | 0.251 | 未达 |
| `c2_0413` | Joseph | 激动反抗 | 0.545 | 勉强 |
| `c2_0419` | Joseph | 紧张 | 0.228 | 未达 |
| `c2_0428` | Joseph | 激动反抗 | 0.607 | 勉强 |
| `c2_0480` | Helena | 兴奋 | 0.295 | 勉强 |
| `c3_0651` | Charles | 激动反抗 | 0.620 | 勉强 |
| `c3_0802` | Joseph | 兴奋 | 0.301 | 勉强 |
| `c3_0803` | Joseph | 兴奋 | 0.175 | 未达 |
| `c3_0839` | Charles | 紧张 | 0.240 | 未达 |
| `c3_0861` | Charles | 紧张 | 0.230 | 未达 |
| `c3_0876` | Charles | 紧张 | 0.227 | 未达 |
| `c3_0942` | Helena | 兴奋 | 0.113 | 未达 |
| `c3_0943` | Helena | 紧张 | 0.231 | 未达 |
| `c3_0944` | Helena | 紧张 | 0.269 | 勉强 |

## 二、电平与峰值

- **voiced RMS**（去静音后能量平均，归一指标）中位 -24.00 dBFS，区间 -24.32 ~ -23.74（跨度 0.58 dB）
- 结论：**已达标**（需求 23 要求 ≤1dB）
- 全段 RMS 中位 -24.5 dBFS，区间 -29.0 ~ -24.0（跨度 5.0 dB）—— 含停顿时长，非归一指标，仅供时长/停顿参考
- 峰值最大 0.744，削波 0 条
