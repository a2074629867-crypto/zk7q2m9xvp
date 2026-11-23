# 强度感知选角表（v3）

把 `intensity` 从「写进计划但没人读」变成「选哪个参考切片」。
排序依据：该切片实测 effort（−z(alpha)+z(f0中位)−z(HNR)，角色内定标）；
**不按 `_1/_2/_3` 序号猜**，序号只是库里的顺序。

| 角色 | 情绪 | 格 | 需求 n(I1/I2/I3) | 切片数 | I1 → I3 选中 | 跃度 | 结论 |
|---|---|---|---|---|---|---|---|
| Thomas | 激动反抗 | loud | 9/53/7 | 4 | loud_1 +0.50 / loud_4 +0.67 / loud_3 +1.08 | +0.58 | 可支撑 |
| Joseph | 平静 | normal | 19/10/0 | 3 | normal_2 -0.53 / normal_1 +0.01 / normal_3 +0.87 | +1.40 | 可支撑 |
| Charles | 紧张 | neutral | 5/20/1 | 3 | neutral_2 -0.47 / neutral_3 -0.32 / neutral_1 +0.30 | +0.77 | 可支撑（库缺档，用退路格） |
| Thomas | 警惕 | scold | 3/14/0 | 3 | scold_3 -0.41 / scold_1 -0.28 / scold_2 -0.16 | +0.25 | 切片太同质 |
| Thomas | 平静 | calm | 13/3/0 | 4 | calm_1 -0.63 / calm_4 -0.49 / calm_3 -0.46 | +0.17 | 切片太同质 |
| Charles | 激动反抗 | angry | 3/10/2 | 1 | angry_1 +0.76 / angry_1 +0.76 / angry_1 +0.76 | - | 切片不足 n=1 |
| Charles | 委屈 | soft | 1/13/0 | 3 | soft_1 -1.51 / soft_2 -1.25 / soft_3 -0.57 | +0.94 | 可支撑 |
| Joseph | 激动反抗 | defiant | 1/9/0 | 3 | defiant_3 +0.08 / defiant_1 +0.12 / defiant_2 +0.44 | +0.36 | 可支撑 |
| Joseph | 紧张 | nervous | 1/9/0 | 3 | nervous_3 -0.85 / nervous_2 -0.44 / nervous_1 +0.44 | +1.29 | 可支撑 |
| Charles | 平静 | neutral | 7/0/0 | 3 | neutral_2 -0.47 / neutral_3 -0.32 / neutral_1 +0.30 | +0.77 | 可支撑 |
| Charles | 警惕 | soft | 2/3/0 | 3 | soft_1 -1.51 / soft_2 -1.25 / soft_3 -0.57 | +0.94 | 可支撑（库缺档，用退路格） |
| Thomas | 兴奋 | loud | 1/4/0 | 4 | loud_1 +0.50 / loud_4 +0.67 / loud_3 +1.08 | +0.58 | 可支撑（库缺档，用退路格） |
| Helena | 兴奋 | excited | 0/3/0 | 3 | excited_2 -0.55 / excited_3 +0.19 / excited_1 +0.26 | +0.80 | 可支撑 |
| Helena | 紧张 | nervous | 0/3/0 | 3 | nervous_2 -0.42 / nervous_3 -0.04 / nervous_1 +0.33 | +0.74 | 可支撑 |
| Thomas | 委屈 | begging | 1/1/0 | 4 | begging_1 +0.76 / begging_2 +1.19 / begging_4 +1.31 | +0.55 | 可支撑 |
| Joseph | 兴奋 | excited | 2/0/0 | 3 | excited_1 -0.29 / excited_2 +0.11 / excited_3 +0.39 | +0.67 | 可支撑 |
| Joseph | 委屈 | wronged | 1/1/0 | 3 | wronged_1 -0.20 / wronged_2 +0.22 / wronged_3 +0.30 | +0.51 | 可支撑 |
| Charles | 兴奋 | excited | 1/0/0 | 3 | excited_1 +0.54 / excited_2 +0.67 / excited_3 +0.90 | +0.36 | 可支撑 |
| Thomas | 紧张 | calm | 1/0/0 | 4 | calm_1 -0.63 / calm_4 -0.49 / calm_3 -0.46 | +0.17 | 切片太同质（库缺档，用退路格） |
| Helena | 平静 | wary | 1/0/0 | 3 | wary_2 -0.38 / wary_3 +0.02 / wary_1 +0.28 | +0.66 | 可支撑（库缺档，用退路格） |
| Helena | 委屈 | wronged | 0/1/0 | 3 | wronged_2 -0.96 / wronged_1 -0.73 / wronged_3 +0.11 | +1.08 | 可支撑 |

## 缺口（需补录同角色同情绪的高低强度参考）

- **Thomas / 警惕**（scold，n=3，跃度 +0.25，需求 17）：切片太同质
- **Thomas / 平静**（calm，n=4，跃度 +0.17，需求 16）：切片太同质
- **Charles / 激动反抗**（angry，n=1，跃度 -，需求 15）：切片不足 n=1
- **Thomas / 紧张**（calm，n=4，跃度 +0.17，需求 1）：切片太同质

## 不变的部分

- 情绪格本身没改：仍是 `rebuild_plan_v2.py` 定的格，跨格借档的情况照样标 `emo_unsupported`。
- 不改语速/降速/电压：本步只换参考切片，`rate` 与后续归一化不变。
- 共用同一句台词文本，换的只是音色参考，所以声纹一致性仍需 `_segcheck_dlg.py` 重新验。
