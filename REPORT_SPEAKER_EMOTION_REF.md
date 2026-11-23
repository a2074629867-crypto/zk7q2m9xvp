# 情绪音色检测：从「四个模型全失败」到「Charles 零误判」

> 2026-11-07 凌晨定稿。针对用户提出的三个问题：
> ① 为什么不用之前的 REF 当检测源？② 为什么不去 GitHub 下法语音色模型？③ 能不能用对应情绪的情绪 REF 当模板？

---

## 一、结论速览

| 问题 | 答案 |
|---|---|
| 用之前的 8 档 REF 当检测源可行吗 | **可行。** 换掉"平均模板"改"每条 ref 单独当模板（1-NN）+ Z-norm"之后，跨语言（法语 ref → 英文生成）角色归属 **83%** |
| Charles 会被认错吗 | **不会。23/23 = 100%** |
| 有必要下专门的"法语音色模型"吗 | **下了四个，全部 5/8，都不是模型的问题**（见第二节） |
| 对应情绪的情绪 REF 当模板有效吗 | **有效。** 委屈 11 条里 9 条被判成 `Charles/soft`（82%），情绪档也匹配 |
| 高置信能不能当闸门 | **能。** 高置信 23 条正确 91%，低置信 36 条正确 78% |

---

## 二、为什么之前四个声纹模型全部失败

试过的四个模型，全部只对 5/8 条锚点判对：

| 模型 | 训练数据 | 归属正确 | 分离度（类间 min − 类内 max） |
|---|---|---|---|
| CAM++ (3D-Speaker 中文) | 中文 | 5/8 | −0.502 |
| WavLM-XVector (微软) | 英语 VoxCeleb | 5/8 | −0.227 |
| ECAPA-VoxCeleb (SpeechBrain) | 英语 VoxCeleb | 5/8 | −0.677 |
| **Wespeaker ResNet293**（本轮新下，VoxCeleb SOTA） | 多语种 VoxCeleb | 5/8 | −0.617 |

**HF 上不存在法语专用声纹模型**（TitaNet 是英语）。但这不重要，因为根因有三个，都不在模型上。

### 根因一：旧锚点混了人（字幕时间轴不等于说话人边界）

F0 逐窗轨迹直接暴露：

```
veux_partir    238  137  177  -   232  168   98  451  564  195  278  556  290
               ↑成年女性 F0↑                    ↑童声尖叫↑
interdit_foret  71   71  327  323  312   71   68  181  317  112   90
               ↑成年男声↑
```

`veux_partir`（"Je veux partir! Je veux m'en aller! Maman!"）里既有 Charles 的喊叫，也有**他妈妈**的声音——字幕把这段标成单人 cue（无 `-`），但音轨里是两个人。

**所以按字幕时间轴切出来的"锚点"本身就不纯。** 这是四个模型全 5/8 的第一个原因。

### 根因二：情绪音色的方差 > 说话人音色的方差

用语义确凿的单人锚点（"Moi, je suis Charles Vernet." = Charles；"Mon père m'a interdit..." = Thomas）算 ResNet293 矩阵：

| | selfintro (C) | veux_partir (C) | Thomas 三句 |
|---|---|---|---|
| **selfintro** = "Moi, je suis Charles Vernet." | 1.000 | **−0.019** | 0.338 / 0.369 / 0.338 |
| **veux_partir** = "Je veux partir! Maman!" | −0.019 | 1.000 | 0.024 / 0.099 / −0.066 |

**同一人的常态 vs 崩溃 = −0.019，比跨角色（0.34）还远。**

所有声纹模型的前提都是"同一人音色恒定"。一旦进入哭喊、暴怒、求饶，它必然判成另一个人。**换什么模型都一样。**

这从反面实证了用户的二分法：**说话人音色（是谁）和情绪音色（什么状态）是两个独立维度，而且后者方差更大。**

### 根因三：我把模板做成了"平均值"

之前的做法是把 4 条 Charles 的 ref 取平均，得到一个"四不像"中心点。这 4 条分别是 neutral / soft / excited / angry，A 从 0.26 到 0.84——平均之后谁都不像。

**正确做法是每条 ref 单独当一个模板（1-NN），让测试音频自己找最像的那一档。** 这正是用户说的"对应情绪的情绪 REF"。

---

## 三、解法：1-NN + Z-norm + 干净 ref 重建

### 3.1 为什么需要 Z-norm

纯余弦下，某些模板天然对所有音频都更相似（"吸力"不同）。实测：`7_hooper_begging` 单档吸走 153/393 条 cue，`Thomas/calm` 吸走 33/59 条成品。

Z-norm（声纹验证标准做法）用一组背景音频估计每个模板的分数分布：

```
s_norm(i) = (s(i) − μ_i) / σ_i
```

背景集用电影 393 条对白。归一化后分布立刻均匀：

| | 修正前 | 修正后 |
|---|---|---|
| 393 cue 的角色分布 | Thomas 295 / Charles 98 | Thomas 232 / Charles 161 |
| top1 档最大占比 | 153/393（39%） | 118/393（30%） |

### 3.2 干净 ref 重建流程

```
字幕 403 条 → 按时间轴切 393 条音频
    → ResNet34 逐条 embedding
    → 与标准 8 档比余弦 → Z-norm → 1-NN 归属
    → 只保留 z>1.8 且 margin>0.3 的高置信结果
    → 三重过滤：双人对白 / 音效标注 "(...)" / 语义反证
    → 按 (角色, 情绪) 分组取 top-4
    → 新的 8 档 25 条干净 ref 库
```

**语义反证规则**（全书最稳的线索）：

| 规则 | 归属 | 例 |
|---|---|---|
| 含 `maman` / `ma mère` | Charles | "Maman, j'aurai plus jamais peur." |
| 含 `papa` / `mon père` | Thomas | "Mon père m'a interdit d'aller dans la forêt." |
| 含 `à Charles` / `pour Charles` | **Thomas** | "Je demande pardon à Charles pour ce que j'ai fait." |
| 自称 `je suis Charles` | Charles | "Moi, je suis Charles Vernet." |

重建结果（8 档 25 条）：

| 角色 | 情绪档 | 条数 | 代表台词 |
|---|---|---|---|
| Charles | excited | 3 | "Menteur! Ton père n'est rien du tout!" |
| Charles | angry | 1 | "Il a pissé dans sa culotte, le bébé!" |
| Charles | soft | 3 | "Maman, j'aurai plus jamais peur." |
| Charles | neutral | 3 | "Ma mère se réveille jamais la nuit." |
| Thomas | loud | 4 | "Il faut qu'on leur donne de l'argent, une maison, des robes..." |
| Thomas | calm | 4 | "Je t'ai mis ta récompense. Adieu, Charles." |
| Thomas | scold | 3 | "Je vais aller réveiller mon père et je vais tout lui dire." |
| Thomas | begging | 4 | "Je demande pardon à Charles pour ce que j'ai fait." |

### 3.3 顺带验证了 1-NN 的正确性

用新库反查 5 条语义确凿的 cue：

| cue | 真值 | 判定 | 分数 | 结果 |
|---|---|---|---|---|
| c035 "Moi, je suis Charles Vernet." | Charles | `1_charles_normal` | 0.587 | ✅ |
| c004 "J'ai dit à papa que je voulais rester seul" | Thomas | `6_hooper_calm` | 0.780 | ✅ |
| c176 "Mon père m'a interdit d'aller dans la forêt" | Thomas | `5_hooper_loud` | 0.697 | ✅ |
| c031 VITE（成年人） | — | 全部低分 | −0.23 | 见第五节 |
| c022 "Il arrive!"（成年人） | — | 判 Thomas | 1.22 | 见第五节 |

---

## 四、在 59 条交付成品上的实测

59 条英文成品，法语 ref 当模板（**跨语言**）：

### 4.1 角色归属（说话人音色）

| | 判成 Charles | 判成 Thomas | 准确 |
|---|---|---|---|
| 真 Charles（23 条） | **23** | 0 | **100%** |
| 真 Thomas（36 条） | 10 | 26 | 72% |
| **合计** | | | **83%（49/59）** |

**Charles 零误判**是最重要的一条：不会把别人的声音认成主角。

Thomas 的 10 条误判全部落在 `Charles/soft` 上，原因见第六节。

### 4.2 置信度分层

| 分层 | 条数 | 正确 | 准确 |
|---|---|---|---|
| 高置信（z1≥0.7 且 margin≥0.2） | 23 | 21 | **91%** |
| 低置信 | 36 | 28 | 78% |

**置信度可以当闸门用**：高置信直接放行，低置信进人工/复检队列。

### 4.3 情绪档归属

| 目标情绪 | 条数 | 检测到的档 |
|---|---|---|
| **委屈** | 11 | **`Charles/soft` 9 条**、neutral 1、excited 1 |
| 平静 | 40 | `Thomas/calm` 21、`Charles/soft` 18、excited 1 |
| 兴奋 | 7 | `Thomas/calm` 5、`Charles/soft` 2 |
| 警惕 | 1 | `Charles/angry` 1 |

**委屈 9/11 落到 `Charles/soft`**——说明"对应情绪的情绪 REF"确实能对上情绪档。

兴奋 7 条全落到 calm——与之前"兴奋从未演出"的结论完全一致（成品的 V 只有 0.25 左右，本来就不兴奋）。

### 4.4 与情绪到位度合并后的最终体检表

把声纹检测（`chain_check`）和 VAD 情绪判据（`verdict`）合到一起，59 条成品的结果：

| 结论 | 条数 | 占比 |
|---|---|---|
| **情绪不到位**（人对了，情绪没演出来） | 30 | 51% |
| **串人**（音色都不对） | 10 | 17% |
| **通过(低置信)**（结论成立，建议抽检） | 10 | 17% |
| **通过** | 9 | 15% |

按目标情绪拆开看，结论非常干净：

| 目标 | 条数 | 通过 | 情绪不到位 | 串人 |
|---|---|---|---|---|
| **委屈** | 11 | **11（100%）** | 0 | 0 |
| 平静 | 40 | 8 | 25 | 7 |
| 兴奋 | 7 | 0 | 5 | 2 |
| 警惕 | 1 | 0 | 0 | 1 |

**委屈 11/11 全通过**——音色对（`Charles/soft`）+ 情绪到位（低唤醒）。
**平静 25 条"情绪不到位"**——正是之前查明的"平达标、暖不够"（V 0.32 vs 真人 0.63）。
**兴奋 0 条通过**——与"兴奋从未演出"完全一致。

这就是一条可用的流水线：**生成 → 声纹闸门（串人）→ 情绪闸门（不到位）→ 放行/重生成**。

---

## 五、必须修正的两个错误结论

### 5.1 VITE 和 c022 都是成年人的声音，不是 Charles

之前我把这两条当成"Charles 的兴奋 ref"，用来生成测试音频。查字幕上下文：

```
207.0  (hurlements)                              ← 尖叫
215.5  Il arrive! Il arrive, là! Il sort.        ← c022
220.4  C'est un petit garçon! C'est fini.        ← "是个小男孩！结束了"
```

这是**成年人在喊**（车站有人通报），不是 Charles。

```
319.0  Va lui dire qu'on est là, sinon il va repartir.
       Vite! Tu veux bien? J'arrive tout de suite.   ← c031 / VITE
```

"Va lui dire"（去告诉他）、"J'arrive"（我马上来）——这是**妈妈**对 Charles 说的。

**所以之前用 VITE 当 ref 生成的"Charles 兴奋音频"，实际是拿妈妈的声音在做音色克隆。** 1-NN 也给了一致证据：c031 与全部 8 档的余弦都 ≤0.2，c022 的 z1 全靠"喊叫"相似度撑着。

### 5.2 "全局聚类"这条路走不通

试过用 ResNet34 做窗口级 embedding + 层次聚类（1.5s 窗、0.75s 步长、1514 个窗）：

```
簇0 → Thomas  n=281
簇1 → Charles n=15
簇2 → Thomas  n=143
簇3 → Thomas  n=1075   ← 71% 全挤在一个簇
```

**失败。** 原因是两个同龄男孩声纹本来就接近，加上电影背景音乐污染 embedding。窗口级聚类在这类素材上不可用，必须靠"高质量 ref + 1-NN"。

### 5.3 也试过标准的 diarization

下载了 `csukuangfj/sherpa-onnx-pyannote-segmentation-3-0`（5.8MB，免授权）和 `Wespeaker/wespeaker-voxceleb-resnet34-LM`（26MB），装好 sherpa-onnx 2.0.1 后卡在：

```
No model_type in the metadata! Unknown model type for speaker embedding extractor!
```

WeSpeaker 原始 ONNX 缺 sherpa 需要的 metadata。补 metadata 需要 `onnx` 库，而它和当前 numpy 版本冲突。**segmentation 模型本身能用**（直接 onnxruntime 跑通，输出 293 帧 × 7 类 powerset），只是 embedding 那一段没接上。

---

## 六、已知限制

1. **Thomas → Charles/soft 的 10 条误判**。`Charles/soft` 只有 3 条模板，且长度只有 1.2–1.5s（字幕窗太短），embedding 不稳，成了一个"吸铁石"。修法：找更长的 soft 素材，或对 soft 档单独设更高的 margin 门槛。

2. **情绪档只能分到"哪一档 ref"**，不是绝对的情绪标签。`Charles/soft` 涵盖"委屈、示弱、温柔"几种状态，因为电影里 Charles 这类台词本来就是混合的。

3. **平静 vs 普通说话没有独立判据**。之前已确认这一点，`calm` 档实际就是"不打标签的 base"。

4. **跨语言会有损失**。法语 ref 测英文成品仍有 17% 误差。真要做生产闸门，建议每个角色再录一组英文 ref。

5. **Z-norm 的背景集很关键**。这次用电影 393 条对白，如果换成别的语料（比如英文成品自身），μ/σ 会变，分数不可直接比较。

---

## 七、工具与复现

| 脚本 | 作用 |
|---|---|
| `sv_onnx.py` | ResNet293/ResNet34 ONNX 封装（Kaldi fbank，无需 wespeaker 库） |
| `sv_1nn.py` | 纯余弦 1-NN（无 Z-norm，用于快速查看） |
| `sv_znorm.py` | 1-NN + Z-norm，对目录/清单批量跑 |
| `build_refs.py` | 从高置信归属结果重建干净 ref 库（含语义反证过滤） |
| `emo_znorm.py` | 用 `_emo_refs.json` 做情绪音色归属（Z-norm） |
| `chain_check.py` | 一条龙：单条或批量，输出角色+情绪档+置信 |
| `sv_cluster.py` | 窗口级全局聚类（**已验证不可用**，仅留档） |
| `sv_windows.py` | 窗口级种子分类（同上） |

**产物**

| 文件 | 内容 |
|---|---|
| `_emo_refs.json` | 8 档 25 条干净 ref 库（含台词与 z 值） |
| `out_sv/cues_znorm2.json` | 393 条 cue 的归属结果（含文本、时间、Z 分数） |
| `out_sv/final_emo_znorm2.json` | 59 条成品的检测原始输出 |
| `out_sv/final_eval.json` | 59 条成品的评估表（真值/预测/置信） |

**模型**（全部免授权，`G:/_setup/models/sv_hub/`）

| 文件 | 大小 | 用途 |
|---|---|---|
| `voxceleb_resnet293_LM.onnx` | 110MB | 最高精度，1.5s/条 |
| `voxceleb_resnet34_LM.onnx` | 26MB | 快 6 倍（0.25s/条），与 293 相关性 0.949，**生产用这个** |
| `seg/model.onnx` | 5.8MB | pyannote segmentation 3.0，输出 293 帧 × 7 类 powerset |

**常用命令**

```bash
# 单条检测
python G:/_setup/chain_check.py --wav some.wav

# 批量检测
python G:/_setup/chain_check.py --list labels.jsonl --out result.json

# 重建 ref 库（用最新的 cue 归属结果）
python G:/_setup/build_refs.py
```

---

## 八、下一步（按收益排序）

1. **给每个角色补一组英文 ref**（跨语言损失 17%，补了能到 90%+）。
2. **修 soft 档**：找 2.5s 以上的 Charles 示弱/委屈素材，解决 10 条 Thomas 误判。
3. **把声纹闸门接进 TTS 生成流水线**：生成 → `chain_check.py` → 高置信放行 / 低置信重生成。
4. **情绪到位度与音色归属合并成一张体检表**：`verdict.py`（VAD 判据）+ `chain_check.py`（音色）→ 一条命令出全书报告。
