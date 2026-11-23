# 对白缺档报告（2026-11-12 01:50）

数据源：`_gate_dlg_v10.json`（239 条对白全量复检）
统计口径：`ref_fallback` = 标注要的情绪档在该角色音色库里不存在，只能用替代档生成，情绪未被验证。

## 一、总览

```
ref_fallback 34 条 / 239 条（14.2%）
  ├─ 真缺档（库里没有，TTS 跑不出来）  32 条
  └─ 选档错（库里有，只是没用）        2 条  ← 可脚本修，需重生成
```

## 二、明细（按 角色 × 情绪）

| 角色 | 想要的情绪 | 实际用的档 | 条数 | 性质 |
|---|---|---|---|---|
| Thomas | 激动反抗 | `Thomas_calm_1` ×8 / `Thomas_begging_1` ×2 | **10** | 真缺档 |
| Thomas | 警惕 | `Thomas_calm_1` ×7 / `Thomas_scold_1` ×5 | **12** | 真缺档（切过，回滚了，见下） |
| Thomas | 兴奋 | `Thomas_loud_1` ×3 / `Thomas_calm_1` ×1 / `Thomas_begging_1` ×1 | **5** | 真缺档 |
| Joseph | 激动反抗 | `Joseph_normal_1` | 2 | 真缺档 |
| Joseph | 紧张 | `Joseph_normal_1` | 1 | 真缺档 |
| Helena | 平静 | `Helena_wary_1` | 1 | 真缺档（Helena 缺 calm） |
| Helena | 委屈 | `Helena_wary_1` | 1 | 真缺档 |
| Charles | 平静 | `Charles_excited_1` | 1 | **选档错**，库里 `Charles_neutral_1` 就有 |
| Joseph | 平静 | `Joseph_nervous_1` | 1 | **选档错**，库里 `Joseph_normal_1` 就有 |

## 三、Thomas 警惕 12 条为什么还缺

2026-11-12 00:50 曾从法语原片切出 `Thomas_wary_1`(c002) / `Thomas_wary_2`(c001) 并云端部署成功，
但 **v8 复检时这 12 条全部从 MANUAL 变成 REGEN（emo_low，实测 0.0 / 0.0004）**。

根因：c001 / c002 是**片头诗歌朗诵**，不是对话表演。e2v 给 0.27 是朗诵腔误判。
拿它当情绪参考音，生成出来零情绪。

已回滚（音频 + 两个 plan 的 voice），并从 `_emo_refs_all.json` 撤掉 `Thomas.wary`。
⇒ **这批要重切，必须过「是否在对话场景」这一关，不能只看 e2v 分数。**

## 四、三个选项与成本

| 选项 | 做法 | 覆盖 | 成本 | 风险 |
|---|---|---|---|---|
| **A 补素材** | 从新片源（Expresso / VCTK 等）切 Thomas 的 defiant / wary / excited 档 | 27 条 | 要新素材 + 云端重生成 | 新朗读者音色与现有 Thomas 不一致，会串味 |
| **B 接受 fallback** | 保持现状，用 calm/scold/loud 替代，交付时标注「情绪未验证」 | 32 条 | 0 | 听感上情绪偏平，但音色一致 |
| **C 选档错 2 条先修** | `c3_0625`→`Charles_neutral_1`、`c1_0046`→`Joseph_normal_1` | 2 条 | 需云端重生成（约 1 分钟） | 无 |

**建议顺序：C（立刻可做）→ B（保底）→ A（只在客户明确要求情绪强度时投入）。**

## 五、与「紧张 / 兴奋」的关系（别混淆）

这两个是**档有、但生成层到不了参考音分位线**，不是缺档：

| 情绪 | 档是否存在 | 实测 n | p25 | max | 参考音 p10 | 处理 |
|---|---|---|---|---|---|---|
| 紧张 | 有（`*_nervous_1`） | 26 | 0.209 | 0.282 | 0.2534 | `HARD_CAP=0.25`，判 MANUAL 不判 REGEN |
| 兴奋 | 有（`*_excited_1`） | 6 | 0.175 | 0.312 | 0.2470 | **2026-11-12 新加 `HARD_CAP=0.32`** |

「兴奋」加入 HARD_CAP 的依据：`c3_0803`(0.177) / `c3_0942`(0.113) 云端重生成后
**字节级无改善**（TTS 确定性输出），说明目标数学上到不了，不是素材问题。

## 六、复现

```bash
# 缺档统计
G:/Python310/python.exe -c "
import json
v=json.load(open('G:/_setup/_gate_dlg_v10.json',encoding='utf-8'))
print(sum(1 for x in v if any(r['code']=='ref_fallback' for r in x['reasons'])))
"
```
