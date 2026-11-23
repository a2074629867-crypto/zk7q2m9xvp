# 对白交付最终报告（七闸 + 短句验收合并）

数据源：`_gate_dlg_v49.json`（239 条）+ `_short_gate_v49.json`

## 一、最终分档

| 类 | 含义 | 条数 | 占比 |
|---|---|---|---|
| A | 七闸全过（声学/声纹/情绪/句内/档内/自然度/音色） | 128 | 53.6% |
| A_S | 短句判据通过（声纹/情绪不可测，改用 内容/电平/静音/自然度） | 45 | 18.8% |
| E | 情绪边缘 / 撞素材数学上限（可听，需人耳） | 59 | 24.7% |
| C | 生成层推不动（情绪贴地/素材上限，需人耳） | 7 | 2.9% |
| D | 短句未过内容判据（需重做/人耳） | 0 | 0.0% |

**验收通过：173 / 239 = 72.4%**
**可听（通过 + 情绪边缘）：232 / 239 = 97.1%**

## 三、生成层推不动（C）

| id | 角色 | 情绪 | 时长 | 原因 |
|---|---|---|---|---|
| c1_0021 | Joseph | 激动反抗 | 4.38s | 生成层推不动（wrong_speaker,emo_marginal） |
| c1_0053 | Joseph | 激动反抗 | 5.46s | 生成层推不动（wrong_speaker） |
| c2_0230 | Joseph | 激动反抗 | 6.87s | 生成层推不动（wrong_speaker） |
| c2_0240 | Helena | 平静 | 4.01s | 生成层推不动（wrong_speaker） |
| c2_0419 | Joseph | 紧张 | 2.92s | 生成层推不动（wrong_speaker） |
| c2_0426 | Joseph | 平静 | 1.94s | 生成层推不动（wrong_speaker） |
| c2_0430 | Joseph | 激动反抗 | 2.00s | 生成层推不动（role_unmeasurable,emo_low） |

## 四、情绪边缘（E，59 条）

| id | 角色 | 情绪 | 值 | 原因 |
|---|---|---|---|---|
| c1_0002 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0005 | Joseph | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0015 | Joseph | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0027 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0031 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0045 | Thomas | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0049 | Joseph | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0050 | Thomas | 委屈 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0051 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0105 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0141 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0146 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0149 | Joseph | 委屈 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0153 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0154 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0158 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c1_0163 | Joseph | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0190 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0194 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0195 | Helena | 兴奋 | 0.299 | 情绪边缘/生成层不可达（role_unmeasurable,emo_marginal) |
| c2_0199 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0234 | Joseph | 激动反抗 | 0.609 | 情绪边缘/生成层不可达（emo_marginal) |
| c2_0242 | Helena | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0248 | Thomas | 激动反抗 | 0.763 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0249 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0257 | Thomas | 激动反抗 | 0.755 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0264 | Thomas | 兴奋 | 0.209 | 情绪边缘/生成层不可达（emo_unreachable) |
| c2_0277 | Charles | 平静 | — | 情绪边缘/生成层不可达（nat_fail) |
| c2_0282 | Thomas | 激动反抗 | 0.710 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0296 | Thomas | 激动反抗 | 0.804 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0299 | Charles | 紧张 | — | 情绪边缘/生成层不可达（intra_drift) |
| c2_0320 | Thomas | 激动反抗 | 0.683 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0324 | Thomas | 警惕 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0358 | Charles | 激动反抗 | 0.615 | 情绪边缘/生成层不可达（emo_marginal) |
| c2_0393 | Thomas | 激动反抗 | 0.796 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0411 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0437 | Thomas | 紧张 | — | 情绪边缘/生成层不可达（ref_poor) |
| c2_0443 | Joseph | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0469 | Charles | 委屈 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0480 | Helena | 兴奋 | 0.295 | 情绪边缘/生成层不可达（emo_marginal) |
| c2_0488 | Thomas | 激动反抗 | 0.877 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c2_0491 | Thomas | 兴奋 | 0.275 | 情绪边缘/生成层不可达（emo_marginal) |
| c2_0501 | Thomas | 激动反抗 | 0.857 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0624 | Thomas | 激动反抗 | 0.800 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0625 | Charles | 平静 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0628 | Thomas | 激动反抗 | 0.789 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0629 | Charles | 激动反抗 | 0.950 | 情绪边缘/生成层不可达（role_unmeasurable,ref_poor) |
| c3_0632 | Thomas | 兴奋 | 0.190 | 情绪边缘/生成层不可达（ref_fallback) |
| c3_0645 | Thomas | 激动反抗 | 0.768 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0802 | Joseph | 兴奋 | 0.357 | 情绪边缘/生成层不可达（role_unmeasurable,emo_marginal) |
| c3_0803 | Joseph | 兴奋 | 0.256 | 情绪边缘/生成层不可达（emo_marginal) |
| c3_0809 | Thomas | 激动反抗 | 0.695 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0838 | Thomas | 兴奋 | 0.226 | 情绪边缘/生成层不可达（emo_unreachable) |
| c3_0860 | Thomas | 激动反抗 | 0.782 | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0874 | Charles | 紧张 | — | 情绪边缘/生成层不可达（nat_fail) |
| c3_0942 | Helena | 兴奋 | 0.113 | 情绪边缘/生成层不可达（role_unmeasurable,hard_cap) |
| c3_0944 | Helena | 紧张 | — | 情绪边缘/生成层不可达（role_unmeasurable) |
| c3_0953 | Charles | 兴奋 | 0.259 | 情绪边缘/生成层不可达（emo_marginal) |
| c3_0954 | Helena | 委屈 | — | 情绪边缘/生成层不可达（role_unmeasurable) |

