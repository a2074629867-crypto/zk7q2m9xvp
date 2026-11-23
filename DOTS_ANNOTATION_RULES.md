# dots.tts 标注规则

> 用途：**给 AI 标注用**。只写「怎么做」，不写研究过程。
> 依据：doteBench V1.0 全库 1,152 例（官方）+ 本项目 40+ 组实测。
> 冲突时以本文件为准；本文件未覆盖的，查 `DOTS_MARKUP_RULES.md`。

---

## 0. 速查表

| 标签 | 什么时候用 | 作用范围 | 取值 | 必须配 |
|---|---|---|---|---|
| `emo` | 文本有明确情绪转折 | **4–11 词**（推荐 8–11） | 9 种 type，`level="2"` | `--use-xvector on` |
| `rate` | 整段要明显快/慢一档 | **整段**（edit 任务） | `0.80` 慢 / `1.25` 快 | 必须走 edit 任务 |
| `pitch` | **不用** | — | — | — |
| `pause` | **不用**（停顿走后期） | — | — | — |
| `sub` `ins` `del` | 改文字 | — | — | 只在 edit 任务，会丢词 |

**默认什么都不打。** 模型自带句法节奏（同一段内语速可在 70–159 wpm 之间自动变化），乱打标签只会破坏它。

---

## 1. 语法：写错 = 静默失效

模型训练时接收的不是标准 XML。写错**不报错，只是标签被忽略**。

| 标签 | ❌ 标准 XML | ✅ 模型格式 |
|---|---|---|
| rate | `<rate factor="0.80">` | `<rate, factor=0.80>` |
| pitch | `<pitch semitones="-5">` | `<pitch, semitones=-5>` |
| pause | `<pause act="ins"/>` | `<pause act="ins" level="2"/>` |
| emo | `<emo type="sad" level="2">` | **不变** |
| sub | `<sub targ="新">旧</sub>` | **不变** |

三条硬规则：

1. **rate / pitch 的属性用逗号分隔，数值不加引号。**
2. **pause 必须带 `level`**，否则等于没写。
3. **数值保留原样**，`1.20` 不能写成 `1.2`（token 序列不同）。

`emo` / `sub` / `ins` / `del` 保持标准 XML 形态，不要转换。

### 1.1 官方粒度四级

官方 `annotations.span_granularity` 的取值：

| 粒度 | 官方占比 | 本项目用法 |
|---|---|---|
| `single_word` | 30% | 不用（会插假声） |
| `short_phrase` | 30% | 不用（偏短） |
| `clause` | 33% | ✅ **主力**（≈8–11 词） |
| `sentence` | 7% | ⚠ 只用于短句（≤11 词） |

**只标 `clause`，必要时标 `sentence`。**

### 1.2 数值约束

- 数值必须有限（不能 NaN / inf）
- `rate` 必须为正数
- 数值原样保留字面形式（`1.20` ≠ `1.2`）

### 1.3 未采用的官方细节

官方 runtime 收到的 `source_text` / `target_text` 带语言前缀（`[EN]` / `[ZH]`）。本项目一直没加，也正常工作，**未验证差异，暂不采用**。

---

## 2. 先选任务

| 要做什么 | 用哪个任务 |
|---|---|
| 生成新内容（正文朗读） | `--task tts`，不带 `source_audio` |
| 同内容重念 / 套语速 / 改文字 | `template_name=edit` + `source_audio` |

**`edit` 只复刻 `source_text`。** 纯文本 instruction 不携带编辑意图时，模型会把 source 念一遍，`target_text` 被忽略，输出长度 ≈ 源音频时长。

---

## 3. `emo` —— 唯一真正生效的表达标签

### 3.1 什么时候打

**只在文本出现明确情绪转折时打。** 判断标准（满足任一条才考虑）：

- 句子里有明确的情绪词或动作（喊、抖、僵住、笑出声、别过脸）
- 语气与上下文反差（平静叙述里突然一句短促的否定）
- 场景事件本身带情绪（发现、被撞见、受伤、威胁）

**不满足就空着。** 一章（约 18 块）总量控制在 **5–10 处**，不是每块都打。

> 为什么稀缺：emo 会让 F0 抬升 15 个半音以上，是「换一种说法」级别的变化，不是微调。每句都打 = 整章都在演。

### 3.2 打多大范围（最容易错的一条）

**官方从来不是逐词打。** 英文 `_phrase` 中位 **8 词**（5–12），`_multi` 每段中位 **6–7 词**（4–11）；
中文 `_phrase` 中位 **11–13 字**（6–20）。官方 span 一律是**语法完整的从句**，0% 是单词。

| span 词数 | 结果 |
|---|---|
| 1 词 | ❌ 该词后插入 0.1s 高频假声，听感像吸气。**官方 0 例** |
| 2–3 词 | ⚠ 偏短，像局部音效。**官方 0 例** |
| **4–7 词** | ⚠ 可用，但情绪扩散不够（官方 multi 常用这档） |
| **8–11 词** | ✅ **一个完整从句，最自然。官方 phrase 主档（中位 8）** |
| 12 词 | ✅ 官方最长用例，正常 |
| 13–20 词 | ⚠ 音色开始下滑 |
| 42 词整段 | ❌ 声纹 0.95 → 0.38，完全不像 |

**取值：优先 8–11 词（与官方主档一致）；最低 4 词；官方上限 12 词（再长音色下滑）。**
且必须是语法完整的片段。

**效果随范围近似线性**（同位置、同 type `sad`）：6 词 **+3.71** 半音 → 11 词 **+6.07** 半音。
想要更明显的情绪，先加词数（到 11 为止），不要指望换更"重"的 type。

### 3.3 打在哪

**位置：句首 / 句中 / 句尾都生效，按语义选，不必强行塞进句中。**

实测（同 type `sad`、同一段文本、只改位置）：

| 位置 | 词数 | 该段 Δ半音 | 声纹 |
|---|---|---|---|
| 句首 | 6 | **+3.71** | 0.9026 |
| 句中 | 6 | **+4.23** | 0.9021 |
| 句尾 | 9 | **+5.36** | 0.8807 |

官方 612 例 phrase 100% 在句中（句首 0、句尾 0），但那是数据集构造偏好，不是模型限制。
**emo 是严格局部的**：包哪一段只有那一段抬高，未包区段全在 ±1 半音内。

**边界：切在连词处。** 官方 span 的前后邻词统计：前 `and`(19) / `that`(12) / `because`(8)；后 `and`(30) / `leaving`(10) / `that`(9)。
优先选：`and` / `but` / `because` / `that` / `so` 之后到下一个逗号或句号之间。

### 3.4 取哪个 type

| type | 中文 | 典型触发 |
|---|---|---|
| `calm` | 平静 | 安抚、叙述性收束、刻意压住 |
| `melancholic` | 忧郁 | 回忆、失落、无力 |
| `sad` | 悲伤 | 明确的哀伤、告别 |
| `afraid` | 恐惧 | 威胁、黑暗、被逼近 |
| `angry` | 愤怒 | 对抗、被激怒、压制性发火 |
| `disgusted` | 厌恶 | 轻蔑、嫌恶、被冒犯 |
| `happy` | 高兴 | 真正的愉悦、放松 |
| `surprised` | 惊讶 | 意外发现、被打断 |
| ~~`neutral`~~ | ~~中性~~ | **不要用**。实测整段会让 F0 +4.6 半音、时长 −19%、高频帧 8.6%→34.9%、声纹 0.95→0.66；整句级与 `calm` 波形相关 **0.9724**，引擎分辨不出两者 |
| ~~`natural`~~ | — | **非法值**。不在官方 9 种枚举内，官方 parser 直接 `raise ValueError`。实测模型不报错但行为不可预期（落点与 neutral/calm 混同），禁止写 |

**`level` 永远写 `"2"`。** 官方 624 例全部是 2，1 和 3 实测无梯度（F0 完全一样）。

`type` 与 `level` **必须同时出现**，缺 `level` 官方 parser 直接报错。

**要「自然」就别打 emo。** 无标签 base 的低频帧占 86%、声纹 0.9506，那才是自然朗读。`calm` / `neutral` 都不是「更平静」，它们是「把声音抬起来」——低频掉到 60%、高频升到 15%，听感偏年轻、偏飘。

### 3.5 必须强制开 xvector

```
--request-option use_xvector=on
```

原因：指令里全是 emo 时，官方 `auto` 会**关闭** speaker guidance，音色改从 8 秒的 voice_ref 取 → 声纹崩到 0.38。强制开启后回到 0.77。

**代价要接受**：即使开了 xvector，音色也会从 0.95 掉到 0.77。emo 是有成本的。

### 3.6 写法示例

```xml
He stopped at the door and <emo type="afraid" level="2">listened to the sound
of his own breathing in the dark hall</emo>, then went in.
```

❌ 错误写法（四种）：

```xml
<emo type="afraid" level="2">He stopped.</emo>              <!-- 太短，插假声 -->
<emo type="afraid" level="2">整段 40 多个词……</emo>          <!-- 太长，毁音色 -->
<emo type="afraid">listened to the sound</emo>               <!-- 缺 level，parser 报错 -->
<emo type="afraid" level="3">listened to the sound</emo>     <!-- level 3 无梯度 -->
```

### 3.7 一句里两个情绪

官方 `_multi` 写法（200 例）允许一句挂两个不同的 emo：

```xml
I can hear <emo type="surprised" level="2">something scraping against the
floorboards</emo> and <emo type="melancholic" level="2">the lights have
suddenly flickered out</emo>.
```

**本项目执行方式**：两个 emo = **sequential 两步**（每步一次生成），不能塞进同一块。音色会累积漂移，所以**一章最多用 1–2 次**。

**不要**在同一块里写两个 emo 然后一次调用。

---

## 4. `rate` —— 语速

### 4.1 只有 edit 任务兑现

| 任务 | 兑现率 | 说明 |
|---|---|---|
| `tts` | **2–6%** | 等于没写 |
| `edit`（整段） | **84–93%** | 线性、不丢词 |

**结论：要语速就切 ≤16s 的段，走 edit 任务套整段 rate。**

### 4.2 粒度反转（必须记住）

| 任务 | 整段 rate | 单词 rate |
|---|---|---|
| `tts` | ❌ 无效 | ✅ 有效（兑现 80%） |
| `edit` | ✅ 有效（84–93%） | ❌ **完全无效**（时长声纹等同 base） |

**在 edit 任务里，不要把 rate 包在单个词上——等于没写。**

### 4.3 取值

官方 451 次 rate 呈**双峰**：

| 档位 | 取值 | 语义 |
|---|---|---|
| 慢档 | **0.80** | 明显慢一档 |
| 快档 | **1.25** | 明显快一档 |

- 标注只用这两个值，不做连续微调。
- **安全下限 0.75**：0.60 需要生成 27s 音频，实测两次 OOM。

### 4.4 代价

| factor | 实测时长（16.16s 基线） | 声纹 |
|---|---|---|
| 1.15 | 14.40s | 0.9104 |
| 1.00 | 16.16s | 0.9506 |
| 0.88 | 17.76s | 0.8724 |
| 0.75 | 20.00s | 0.7994 |

**放慢越多，音色越淡。**

---

## 5. `pitch` —— 禁用

**不要写。** 两种任务下都无效：

- 整段 -6 半音：只降 1.20 半音（兑现 20%）
- 整段 -12 半音：只降 0.28 半音（**比 -6 更小**）
- 词级：+0.05 半音，完全不动

不线性、不单调，等同于噪声。写了不会让声音变低，只会白占标签位。

---

## 6. `pause` —— 禁用

**不要写进文本。** 原因不是无效（模型格式下它有效），而是它会**改变句法感知**：

> `Dinosaur figurines, picture books, and a paper mache giraffe.`
> → 被念成 `Dinosaur figurines. Picture books. And a paper mache giraffe.`

逗号列举被拆成三个独立句。停顿的正确做法是后期插入（`insert_pauses.py`，按马修实测分布：逗号 1.17s / 句号 1.76s / 段落 2.50s）。

---

## 7. 文本编辑标签 `sub` / `ins` / `del`

只在 edit 任务、需要改文字时用。**会丢词**：实测替换第一句后，后面的 `and a paper mache giraffe` 被吞掉，逗号还变成了句号。

生成正文不要用它——正文用 `--task tts` 直接给文本。

### 7.1 其余标签：一律不用

| 标签 | 状态 |
|---|---|
| `<bg>` | 背景音，未测，**不用** |
| `<enhance>` | 实测无效（+0.16 半音），**不用** |
| `<spk_transfer/>` | 音色迁移，本项目不需要，**不用** |
| `<emo desc="...">` | 与 `type` 互斥的另一种写法，未测，**不用** |

---

## 8. 组合规则

### 8.1 emo 与 rate 互斥

实测：纯 `rate 0.88` → 17.76s（兑现 84%）；加上 emo 后 → 16.32s（**兑现 0%**）。

**同一块里不要同时写 emo 和 rate。**

### 8.2 官方范式（供参考，本机不兑现）

官方 `compositional` 集里 emo + rate 共 33 例，特征是：

- **包不同片段，从不重叠**
- rate 只取 `0.8` / `1.25`
- 顺序无关

但本机实测 rate 会被 emo 抑制，所以**这条只记录不执行**。

### 8.3 真要两者都有：sequential 两步（实测过，代价明确）

```
第一步：生成 emo 版（tts 或 edit）
第二步：把第一步的输出当 source，套整段 rate（edit，同内容复刻）
```

实测（source 用 11 词 `sad` 版，HEAD 原本 +6.07 半音）：

| 指标 | 结果 |
|---|---|
| rate 兑现 | **67%**（17.12 → 20.00s，理论 21.40s）——与纯 rate 的 67% 完全一致 |
| emo 保留 | **约 20%**（HEAD +6.07 → **+1.04**） |
| 声纹 | 0.8858 → **0.7569** |

**rate 完全不受影响，但 emo 被抹掉八成。** 因为第二步是「拿第一步的输出当 source 再复刻一遍」，
复刻时模型按自己的韵律重排，第一步的局部抬升被压平。

**所以「又慢又有情绪」不要用 sequential**，改走：

```
单步 emo（音色 0.8858、情绪完整） → 后期 rubberband 0.88x（音色 0.784）
```

音色代价相当（0.7569 vs 0.784），但情绪一点不丢。

---

## 9. 禁令清单

标注时逐条对，违反任一条输出就会坏：

1. **不嵌套、不交叉。** `Operations cannot nest or cross` —— `<rate><emo>…</emo></rate>` 非法。
2. **不写 `pitch`。**
3. **不把 `pause` 写进文本。**
4. **`emo` 不超过 12 词**（官方最长用例），推荐 8–11 词。
5. **`emo` 不包 1 个词。**
6. **`emo` 的 `level` 只写 2**，且必须写。
7. **`emo` 不加 `--use-xvector on` 会毁音色。**
8. **`tts` 任务下不指望 `rate`。**
9. **`edit` 任务下不把 `rate` 包在单词上。**
10. **`emo` 与 `rate` 不同块。**
11. **不逐句打 `emo`**，一章 5–10 处。
12. **不写 `bg` / `enhance` / `spk_transfer` / `emo desc`。**
13. **同一块默认只写 1 处 `emo`。** 确需两处（不同情绪、不同片段）可以——实测两处各自生效、互不串扰
    （`sad` +3.38 / `surprised` +13.54），但声纹从 0.89 掉到 **0.8406**，且块时长 +14.8%。
14. **`type` 只能取 9 种枚举之一**：`angry afraid sad happy surprised disgusted melancholic calm neutral`（`neutral` 见 3.4，实际也别用）。写 `natural`、`naturl` 之类，官方 parser 直接 `raise ValueError`。

---

## 10. 标注流程

```
1. 切块        按句边界累加到 ≤130 词
2. 读块        判断这一块的情绪走向（升 / 降 / 平）
3. 找转折点    每块 0–1 个为主，强转折才给 2 个；没有就空着
4. 选片段      8–11 词，切在连词边界，语法完整
5. 定 type     查 3.4 表
6. 写标签      <emo type="X" level="2">…</emo>
7. 校验        MK.validate() 过一遍
```

第 4 步是唯一容易出错的环节。**判断标准：把这段文字单独摘出来，读起来是不是一个完整的语义单元？** 不是就换边界。

### 10.1 一个标注好的块（照这个样子写）

原文：

```
He did not answer. The hall was longer than he remembered, and the door at the
end of it stood half open. He could hear something inside, a small dry sound,
like paper moving. His hand stayed on the banister. Then he went up.
```

标注后：

```
He did not answer. The hall was longer than he remembered, and the door at the
end of it stood half open. He could hear <emo type="afraid" level="2">something
inside, a small dry sound, like paper moving</emo>. His hand stayed on the
banister. Then he went up.
```

要点：9 词、在句中、前面切在 `hear` 之后的从句起点、后面接句号。整块只此一处。

---

## 11. 检查清单

提交前逐条打勾：

- [ ] 每个 `emo` 的 `level` 都是 `"2"`，且 `type` 与 `level` 同时存在
- [ ] 每个 `emo` span 在 4–11 词之间
- [ ] 每个 `emo` 都在句中（不在句首、不在句尾）
- [ ] 每个 `emo` 的边界落在连词或逗号处
- [ ] 没有嵌套、没有交叉
- [ ] 没有 `pitch`
- [ ] 没有 `pause`
- [ ] 同一块里没有 emo + rate 并存
- [ ] 同一块里没有两个 emo
- [ ] 没有 `bg` / `enhance` / `spk_transfer`
- [ ] 调用参数里有 `use_xvector=on`
- [ ] 全章 emo 数量在 5–10 之间

---

## 12. 一句话总结

> **只打 `emo`，8–11 词，切在连词上，`level="2"`，配 `--use-xvector on`，一章 5–10 处。**
> **语速走 edit 任务的整段 `rate`（0.80 / 1.25）。**
> **pitch 和 pause 不写。**

---

## 附：文件位置

| 文件 | 用途 |
|---|---|
| `G:/_setup/dots_markup.py` | 标签构造 + 校验，**所有标签都从这里生成，不要手写字符串** |
| `G:/_setup/DOTS_ANNOTATION_RULES.md` | 本文件（标注手册） |
| `G:/_setup/DOTS_MARKUP_RULES.md` | 完整技术规则 + 全部实测数据 |
| `G:/_setup/DOTS_EMO_SPEC.md` | 官方 emo 示范原文 + 量化分布 |
