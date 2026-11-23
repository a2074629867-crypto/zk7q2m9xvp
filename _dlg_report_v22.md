# 对白链路交付报告

数据源：`_gate_dlg_v22.json`（239 条）

## 一、分层（互斥，共 239 条）

| 类 | 含义 | 条数 | 占全量 |
|---|---|---|---|
| A | 通过（声学+声纹+情绪全过） | 98 | 41.0% |
| B | 待重生成（真缺陷） | 1 | 0.4% |
| G | 音色一致性异常（句内突变/换人/档内离群，第 4+5 闸） | 14 | 5.9% |
| H | 自然度不达标（NISQA+SQUIM 下限筛，第 6 闸） | 3 | 1.3% |
| C | 素材不可用（缺档 / 参考片段质量不达标，需换素材） | 12 | 5.0% |
| D | 短句未验收（声学指标不成立） | 73 | 30.5% |
| E | 情绪边缘 / 生成层不可达（p10~p25、撞数学顶、结构性推不动） | 36 | 15.1% |
| F | 待人工 | 2 | 0.8% |

**严格通过：98 条（41.0%）**

**可听（含边缘需人耳）：134 条（56.1%）** —— A 98 + E 36

**需要动音频：30 条** —— B 待重生成 1 + G 音色一致性 14 + H 自然度 3 + C 缺档 12

**测不了（不是坏）：75 条** —— D 短句 73 + F 待人工 2

### D 短句按词数

| 词数 | 条数 |
|---|---|
| 1 | 21 |
| 2 | 11 |
| 3 | 11 |
| 4+ | 30 |

> 1-3 词条目上，声纹 embedding 与 F0 统计不成立（0.5s 不足以刻画说话人）。这类**不能判 PASS，也不能算坏**，交付时单列。

### C 缺档明细（素材缺口）

| 角色 | 情绪 | 条数 | 可解性 |
|---|---|---|---|
| Thomas | 激动反抗 | 3 | 档已补齐，重跑可解 |
| Thomas | 警惕 | 3 | 档已补齐，重跑可解 |
| Joseph | 激动反抗 | 2 | 档已补齐，重跑可解 |
| Joseph | 紧张 | 1 | 档已补齐，重跑可解 |
| Thomas | 委屈 | 1 | 档已补齐，重跑可解 |
| Helena | 平静 | 1 | 素材仍缺 |
| Helena | 委屈 | 1 | 档已补齐，重跑可解 |

> 详见 `_missing_refs_report.md`。「素材仍缺」= TTS 重跑变不出来；「档已补齐」= 重跑就能解决，只是还没重跑。

### B 待重生成明细

| id | 角色 | 原因 | 文本 |
|---|---|---|---|
| `c2_0487` | Charles | emo_low | ‘What are you going back into the house for? |

### 音色一致性异常（第 4+5 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0149` | Joseph | intra_drift | ‘It’s easy for you to despise and shrug  |
| `c2_0217` | Thomas | intra_switch, ref_fallback, role_unmeasurable | ‘It is my house,’ he thought, ‘it is pri |
| `c2_0291` | Charles | scs_outlier | ‘Well, my mother can’t afford to buy us  |
| `c2_0321` | Charles | intra_drift | ‘I told you. When he was in the Battle o |
| `c2_0326` | Thomas | intra_drift, role_unmeasurable | Hooper raised his eyebrows, ‘I should th |
| `c2_0356` | Charles | scs_outlier | ‘I’m supposed to, that’s what your fathe |
| `c2_0371` | Thomas | intra_switch, ref_fallback | ‘Only schools for poor people. Boarding  |
| `c2_0372` | Charles | scs_outlier | ‘It’s... I don’t know. I daresay my fath |
| `c2_0437` | Thomas | emo_marginal, intra_drift, ref_poor | ‘Oh. Are they going to stay, then?’ |
| `c2_0471` | Charles | scs_outlier | ‘They do fall. They fall on their own.’ |
| `c3_0625` | Charles | intra_drift, scs_outlier | ‘There isn’t any key.’ |
| `c3_0834` | Thomas | intra_drift | ‘Go on then,’ he said in a soft voice, ‘ |
| `c3_0840` | Thomas | intra_drift | ‘My grandfather. Haven’t you ever heard  |
| `c3_0953` | Charles | emo_marginal, intra_switch, scs_outlier | He wrote home, ‘I like it here very much |

### 自然度不达标（第 6 闸） 明细

| id | 角色 | 判因 | 文本 |
|---|---|---|---|
| `c1_0046` | Joseph | nat_fail | ‘Yes.’ |
| `c2_0306` | Thomas | emo_marginal, nat_fail, role_unmeasurable | ‘It was years ago, dozens of years. It w |
| `c3_0838` | Thomas | emo_unreachable, nat_fail, tail_abrupt | ‘Yes, every sort of moth in the world.’ |

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
| `c2_0264` | Thomas | 兴奋 | — | None |
| `c2_0298` | Thomas | 警惕 | 0.002 | 勉强 |
| `c2_0299` | Charles | 紧张 | 0.222 | 未达 |
| `c2_0308` | Thomas | 警惕 | 0.003 | 勉强 |
| `c2_0312` | Charles | 紧张 | 0.247 | 未达 |
| `c2_0314` | Charles | 紧张 | 0.262 | 勉强 |
| `c2_0327` | Charles | 紧张 | 0.251 | 未达 |
| `c2_0328` | Thomas | 警惕 | 0.001 | 勉强 |
| `c2_0413` | Joseph | 激动反抗 | 0.545 | 勉强 |
| `c2_0419` | Joseph | 紧张 | 0.228 | 未达 |
| `c2_0428` | Joseph | 激动反抗 | 0.607 | 勉强 |
| `c2_0480` | Helena | 兴奋 | 0.295 | 勉强 |
| `c2_0491` | Thomas | 兴奋 | — | None |
| `c3_0632` | Thomas | 兴奋 | — | None |
| `c3_0651` | Charles | 激动反抗 | 0.620 | 勉强 |
| `c3_0802` | Joseph | 兴奋 | 0.301 | 勉强 |
| `c3_0803` | Joseph | 兴奋 | 0.175 | 未达 |
| `c3_0826` | Thomas | 兴奋 | — | None |
| `c3_0839` | Charles | 紧张 | 0.240 | 未达 |
| `c3_0861` | Charles | 紧张 | 0.230 | 未达 |
| `c3_0876` | Charles | 紧张 | 0.227 | 未达 |
| `c3_0922` | Charles | 紧张 | 0.241 | 未达 |
| `c3_0942` | Helena | 兴奋 | 0.113 | 未达 |
| `c3_0943` | Helena | 紧张 | 0.231 | 未达 |
| `c3_0944` | Helena | 紧张 | 0.269 | 勉强 |

## 二、电平与峰值

- **voiced RMS**（去静音后能量平均，归一指标）中位 -24.00 dBFS，区间 -24.01 ~ -23.96（跨度 0.05 dB）
- 结论：**已达标**（需求 23 要求 ≤1dB）
- 全段 RMS 中位 -24.5 dBFS，区间 -27.1 ~ -24.0（跨度 3.1 dB）—— 含停顿时长，非归一指标，仅供时长/停顿参考
- 峰值最大 0.744，削波 0 条

## 三、本轮变化（对比 `_gate_dlg_v21.json`）

| 类 | 上一版 | 本版 | 变化 |
|---|---|---|---|
| A | 94 | 98 | +4 |
| B | 1 | 1 | +0 |
| G | 20 | 14 | -6 |
| H | 2 | 3 | +1 |
| C | 12 | 12 | +0 |
| D | 73 | 73 | +0 |
| E | 35 | 36 | +1 |
| F | 2 | 2 | +0 |

- **A** 新进 4 ['c2_0265', 'c2_0271', 'c2_0365', 'c2_0368'] ｜ 移出 0 
- **G** 新进 0  ｜ 移出 6 ['c2_0265', 'c2_0271', 'c2_0306', 'c2_0365', 'c2_0368', 'c3_0922']
- **H** 新进 1 ['c2_0306'] ｜ 移出 0 
- **E** 新进 1 ['c3_0922'] ｜ 移出 0 
