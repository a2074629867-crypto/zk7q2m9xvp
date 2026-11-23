# dots.tts 标记规则（技术全档）

> **标注时看 `DOTS_ANNOTATION_RULES.md`（精简手册），不要看这份。**
> 本文件是技术全档：语法、官方常量、全部实测数据、作废声明、改动记录。
> 单一事实来源。所有生成脚本必须经 `dots_markup.py` 构造标签，不要手写 XML 字符串。
> 官方来源：`studio-dots-ai/dots.tts` README、`doteBench/docs/data.md`、
> `doteBench/src/dotebench/candidates/dots_tts_edit/compile.py`

---

## 一、两种格式，别混

| | 标准 XML（人写 / 评测集契约） | 模型格式（实际喂给模型） |
|---|---|---|
| rate | `<rate factor="1.20">faster</rate>` | `<rate, factor=1.20>faster</rate>` |
| pitch | `<pitch semitones="4">higher</pitch>` | `<pitch, semitones=4>higher</pitch>` |
| pause | `<pause act="ins"/>` | `<pause act="ins" level="2"/>` |
| emo | `<emo type="calm" level="2">x</emo>` | 同左（不转换） |
| sub | `<sub targ="new">old</sub>` | 同左（不转换） |

**差异三条**：属性分隔符是**逗号**不是空格；数值**不加引号**；`<pause>` **必须带 level**。

`compile.py` 原注释：

```
Read attribute strings directly: float conversion would lose lexical
precision (for example 1.20), changing the model's token sequence.
```

⇒ 数值的词法形式会改变 token 序列。`1.20` ≠ `1.2`。构造时按目标精度直接格式化，
不要先转 float 再拼字符串。

**用 `MK.to_model_format(xml)` 转换，不要手写。**

---

## 二、官方常量

### 情绪 type（8 种）

`angry` `afraid` `sad` `happy` `surprised` `disgusted` `melancholic` `calm`

来源：doteBench emotion 集 612 例的实际取值分布
（disgusted 110 / angry 109 / melancholic 109 / happy 109 / sad 109 / surprised 109 / afraid 109 / calm 52）。

### 强度 level

`1` `2` `3`。`data.md`：「Emotion levels are 1–3」。官方样例全部用 `2`。

### 停顿 act

`ins`（插入）/ `red`（减少）。pause 集 300 例：ins 298 / red 302。
模型格式必须带 level，官方适配器固定 `level="2"`。

### 粒度（官方支持到词级）

prosody 集 360 例的 `span_granularity` 分布：

| 粒度 | 例数 | 占比 |
|---|---|---|
| `single_word` | 108 | 30% |
| `short_phrase` | 108 | 30% |
| `clause` | 120 | 33% |
| `sentence` | 24 | 7% |

⇒ **词级 rate/pitch 是设计内的能力**，不是滥用。

---

## 三、三条铁律（官方 `data.md`）

1. **Operations cannot nest or cross** —— 不能嵌套、不能交叉
2. **所有操作都是局部的**
3. **xvector 自动开关**

| 指令里含 | xvector | 音色来源 |
|---|---|---|
| 只有 `emo` / `bg` / `enhance` | 自动**关闭** | `voice_ref` |
| 含 `sub`/`ins`/`del`/`pitch`/`rate`/`pause` | 自动**开启** | `source_audio` |

可用 `--use-xvector on|off` 强制覆盖。

**本项目音色来自 `source_audio`。若要只用 emo，必须显式 `--use-xvector on`。**

---

## 四、多操作用 sequential，别一次塞

| 方式 | 行为 |
|---|---|
| `one_take` | 整条指令一次调用 |
| `sequential` | 先文本标签（sub/ins/del），再声学标签（emo/pitch/rate/pause），**每个操作单独一步**，上一步输出作为下一步输入 |

`planner.py`：`Execute text tags first, then acoustic tags, preserving each XML order.`

代价：N 个操作 = N 次生成，时间线性增长，且每步重新生成会累积音色漂移。

---

## 五、构造 API

```python
import dots_markup as MK

MK.rate("text", 0.83)            # <rate, factor=0.83>text</rate>
MK.pitch("text", 3)              # <pitch, semitones=3>text</pitch>
MK.pause("ins", 2)               # <pause act="ins" level="2"/>
MK.emo("text", "calm", 2)        # <emo type="calm" level="2">text</emo>
MK.sub("old", "new")             # <sub targ="new">old</sub>

MK.to_model_format(xml)          # 标准 XML → 模型格式
MK.validate(xml)                 # → (ok, errors, warnings)
MK.needs_xvector(xml)            # → True/False
MK.describe(xml)                 # → "rate×3 · pause×2"
MK.merge_adjacent_rate(xml)      # 合并相邻同 factor 的 span（中间只有空白时）
```

`validate()` 除结构检查外，还按本项目经验给两类 warning：
`rate` 与 `pause` 混用、`rate` span 数 > 6。warning 不阻止输出。

`MK.PAUSE_SECONDS` 是本项目的停顿目标（母带 26.92min / 641 间隙实测）：
句号 1.76 / 逗号 1.17 / 分号冒号 1.28 / 段落 2.50 / 换气 0.20 / 词间微隙 0.10。

---

## 六、生成策略

### 语速不要指望标签（详见第七节）

`<rate>` 整段包裹实测兑现率只有 2–6%，与数值大小无关。所以：

- **整章/整块的语速** → 后期 rubberband / atempo，不要写进标签
- **`<rate>` 只用于单词级表演**（某个词强调、某个词拖长），且要接受丢词风险
- **停顿** → `insert_pauses.py` 后期插（真人停顿素材）

### 默认：不打 rate，停顿走后期

```bash
dots_prosody.py --in text.txt --mode flat --target-wpm 145
```

`--emit-pause-tags` 默认关闭（pause 会改标点层级）。

三条必须遵守的行为：

1. **不生成 `<pause>` 标签**。停顿全部后期插入。
2. **相邻同 factor 的 span 自动合并**（`merge_adjacent_rate`），减少标签数。
3. **标点必须留在文本里**。缺句读会影响模型对节奏的判断；
   早期版本把标点当作独立字段丢弃，等于喂给模型一段没有标点的文字。

### 如果确实要打 rate

按句拆 span 的上限是 **10**（9 span 实测 131/131 不丢词，29 span 丢 23% 词）。
`chapter_run.py` 的 `merge_to_limit()` 会强制压到 10 以内。

但要清楚：**拆 span 对语速的改善只有 2–6%，不值得为它重跑整章。**

---

## 七、官方怎么调语速：只有词级 rate，没有全局 speed

### 官方根本没有 speed 参数

`runtime.generate()` 的全部参数：

```
text, prompt_audio_path, prompt_text, template_name, language,
speaker_scale, ode_method, num_steps, guidance_scale
```

**没有 speed / duration / rate 数值参数。** CLI 也只有 `--max-generate-length`
（最大 audio patch 数，是输出上限，不是语速）。

⇒ 唯一手段是 `<rate factor="x">` 标签。

### factor 的官方取值范围（prosody 集 360 例实测统计）

| 取值 | 次数 | 取值 | 次数 |
|---|---|---|---|
| 0.81 | 36 | 1.12 | 24 |
| 1.20 | 23 | 1.32 | 22 |
| 0.95 | 20 | 0.97 | 19 |
| 1.16 | 17 | 1.19 | 17 |
| 0.89 | 14 | 1.28 | 14 |

极端值只有 0.67、1.99 各 1 次。**主流区间 0.76–1.32，即 ±25% 以内。**

### 官方粒度：三成是单词级

`single_word` 108（30%）/ `short_phrase` 108（30%）/ `clause` 120（33%）/ `sentence` 24（7%）

官方样例原文：

```xml
"Yes, yes," she <rate factor="1.12">hurried</rate>, pulling her hand
<rate factor="0.88">gently</rate> away from him.
```

⇒ **它是给单个词加表演（hurried 加快、gently 放慢），不是整段调速。**

### 官方评测指标

`evaluation.md`：

```
| Prosody | Absolute pitch-shift error in semitones and duration error in seconds |
```

⇒ 官方确实按「时长误差（秒）」考核 rate，不是只看听感。

### 实测：整段无效，词级有效

131 词 / seed 42 / 同一 voice_ref / 同一文本：

| 用法 | 总时长 | 相对基线 |
|---|---|---|
| 无标签 | 52.32s | — |
| 整段 rate 0.80（`tts` 模板） | 55.52s | +6.1% |
| 整段 rate 0.80（`instruction_tts` 模板） | 52.96s | +1.2% |
| 整段 rate 0.50（`instruction_tts`） | 53.60s | **+2.4%** |
| **词级 rate 0.50（只包 `tussle`）** | 48.64s | 该词 **0.40s → 0.72s（+80%）** |

三条结论：

1. **整段包裹基本无效，且与数值大小无关** —— rate 0.50 应该 +100%，实际 +2.4%。
2. **词级有效，兑现率约 80%**（目标 +100%，实测 +80%）。
3. **模板不是原因** —— `[带指令文本]` 前缀（`instruction_tts`）也没让整段 rate 生效。

### 为什么

模型训练分布是「局部改某个词」，整段包裹超出分布，标签被忽略。
与 xvector、XML 格式、模板都无关。

### 词级 rate 的代价

实测总长 52.32 → 48.64s（−7%），词数 131 → 124（**丢 7 词**）。
它不是免费的：局部放慢会挤压其他地方，还会吞词。

### 结论

**dots.tts 没有「整段语速」能力。** `<rate>` 是逐词表演工具，不是朗读速度旋钮。

整章慢读只能走后期：

| 手段 | 0.88x 时的声纹 |
|---|---|
| rubberband | **0.784** |
| atempo | 0.701 |
| asetrate（降调） | 0.369（毁音色） |

---

## 八、官方怎么表达语气语调（词句表演）

### 8.1 官方只有两个「表演」标签：`<rate>` 和 `<pitch>`

doteBench 的 **prosody 集 360 例**，标签分布极其干净：

| 组合 | 例数 |
|---|---|
| 只有 `rate` | 120 |
| 只有 `pitch` | 120 |
| `pitch` + `rate` 混用 | 120 |

**没有任何 emo、pause 混进来。** 官方的「韵律表演」就是这两个标签。

### 8.2 pitch 的取值：-9 到 +9 半音，主流 ±6

| 半音 | 次数 | 半音 | 次数 |
|---|---|---|---|
| -7 | 7 | +3 | 54 |
| -6 | 38 | +4 | 36 |
| **-5** | **66** | **+5** | **55** |
| -4 | 43 | +6 | 26 |
| -3 | 31 | +9 | 7 |
| -2 | 21 | +2 | 14 |

**负值略多于正值**（-6 到 -2 共 199 次 vs +2 到 +6 共 185 次）。
单例里 pitch 的 span 数：1 个 125 例 / 2 个 71 例 / 3 个 44 例。

### 8.3 官方示例的写法：只包单词，不包整句

```xml
"Yes, yes," she <rate factor="1.12">hurried</rate>, pulling her hand
<rate factor="0.88">gently</rate> away from him. Presently it stole back
to his coat sleeve.
```

```xml
He guessed there <pitch semitones="-5">must</pitch> be a
<rate factor="1.12">lively</rate> fire in that room beyond.
```

三条共同点：

1. **标签只包一个词**（`hurried` / `gently` / `must` / `lively`），从不包整句
2. 同一句里多个 span，作用在**不同词**上
3. `pitch` 与 `rate` **不嵌套**，各管各的词

粒度分布（`annotations.span_granularity`）：
`single_word` 108（30%）/ `short_phrase` 108（30%）/ `clause` 120（33%）/ `sentence` 24（7%）

**七成是单词或短词组级，整句只有 7%。**

### 8.4 emo 的三种官方写法（完整原文见 `DOTS_EMO_SPEC.md`）

emo 集 612 例（intense 300 + neutral 312），每种写法各占三分之一（100/100/100 与 104/104/104）。

**官方用同一段音频（sha256 `e5f60b48…`）、同一段文本做了三版对照，只改 emo 的作用范围：**

```xml
<!-- _whole：整段包住 -->
<emo type="angry" level="2">I can hear something scraping against the floorboards
just outside my bedroom door and the lights have suddenly flickered out leaving me
completely alone in the freezing darkness of this empty house tonight.</emo>

<!-- _phrase：只包中间一个从句 -->
I can hear something scraping against the floorboards just outside my bedroom door
and <emo type="melancholic" level="2">the lights have suddenly flickered out</emo>
leaving me completely alone in the freezing darkness of this empty house tonight.

<!-- _multi：一句里两个不同情绪 -->
I can hear something <emo type="happy" level="2">scraping against the floorboards
just outside my bedroom door</emo> and the lights have suddenly flickered out
<emo type="disgusted" level="2">leaving me completely alone in the freezing
darkness</emo> of this empty house tonight.
```

**量化特征（624 个 span 实测）：**

| 项目 | 数值 |
|---|---|
| `_phrase` 长度 | 英文中位 **8 词**（5–12）／ 中文中位 **11–13 字**（6–20）；**单词 0%** |
| `_multi` 每段长度 | 英文中位 **6–7 词**（4–11）／ 中文 **7–11 字** |
| `_whole` 长度 | 英文中位 28–33 词（16–44）／ 中文 30–46 字 |
| span 位置 | phrase **全部在句中**（句首 0、句尾 0）；我们实测句首/句尾也生效 |
| span 边界词 | 前：and 19 / that 12 / because 8；后：and 30 / leaving 10 / that 9 |
| `level` | **624 例全部是 2**，0 个 1、0 个 3 |
| 情绪枚举 | parser 允许 **9 种**（含 `neutral`），样例出现 8 种 |

> ⚠ 此前写「phrase 中位 2–3 词」是统计错误：数据集**中英各半**，中文用 `split()` 会把整句算成「1 词」。
> 按语言分开重算后，英文中位 8 词、中文中位 11–13 字，**没有一个 span 是单词**。
> 单词级标签是 `rate`/`pitch`（prosody 集），不是 `emo`。

**两条更正我此前的说法：**

1. `_multi` 的情绪**不是乱标**。`neutral` 集的例子是 `calm` + `happy`，都贴合语义。
   只有 `intense` 集因为任务是「改情绪」（源全是 afraid），才会出现语义不匹配。
   **我们的源是平静朗读，对应 `neutral` 场景**，情绪应当贴合文本。
2. **`level` 不是「官方支持 1–3」就能用**。parser 接受，但训练数据里只有 2，
   所以模型对 1/3 无梯度（实测 F0 181.3 / 182.3 / 180.8 完全一致）。**永远写 2。**

**官方 parser 硬约束**（`parser.py:58`，违反直接报错）：

```python
if kind not in ATTRS or set(attrs) != ATTRS[kind] or len(node):
    raise ValueError(...)
```

- `type` 与 `level` **必须同时存在**（`<emo type="sad">` 非法）
- **不能有多余属性**
- **不能嵌套**

**官方 runtime 收到的字段**（`compile.py`）：

- `source_text` == `target_text` == 剥掉所有标签的纯文本（emo 不改任何字符）
- 两者都带 `[EN]` / `[ZH]` 前缀（`compile_public_runtime_request`）
- `<emo>` **不做格式转换**，原样进入模型（只有 pitch/rate/pause 要转逗号格式）

**多情绪必须分步**：`planner.py` 规定「文本标签先、声学标签后，每操作一步」。
`_multi` 两个 emo ⇒ sequential 模式下是 **2 次生成**，音色会累积漂移。

### 8.5 ★ 官方数据集是「严格分离」的：情绪集里一个 rate 都没有

这是查完 doteBench 全库（1,152 例）之后最该记住的一条：

| 数据集 | 例数 | 含 rate | 含 pitch | 含 emo | 含 pause |
|---|---|---|---|---|---|
| `prosody/default` | 360 | **240** | **240** | **0** | 0 |
| `emotion/intense` | 300 | **0** | **0** | 300 | 0 |
| `emotion/neutral` | 312 | **0** | **0** | 312 | 0 |
| `pause/default` | 300 | 0 | 0 | 0 | 300 |
| `compositional/default` | 240 | 69 | 69 | 138 | 138 |

**结论：官方的「情绪」实验里没有任何 rate / pitch / pause，「韵律」实验里没有任何 emo。**
两者只在 `compositional`（组合集）里同时出现。所以：

- **emo 的官方示范里没有 rate** —— 612 例 emo 样例，rate 出现 0 次
- 想「又改情绪又改语速」时，官方唯一给出的范式在组合集里

### 8.5.1 官方 emo + rate 的唯一范式：分片段，各管各的

组合集里含 `emo` 和 `rate` 的共 **33 例**（纯双标签 `emo+rate` 15 例，其余带第三标签）。

| 项目 | 实测值 |
|---|---|
| rate 取值 | **只有两个：`0.8`（17 次）、`1.25`（16 次）** |
| emo 类型 | 8 种平均分布（angry 5、afraid 5、happy/sad/disgusted/melancholic/calm 各 4、surprised 3） |
| emo span 词数 | 中位 **1**（1–9） |
| rate span 词数 | 中位 **1**（1–6） |
| 出现顺序 | rate 在前 18 / emo 在前 15（**顺序无关**） |

**核心特征：emo 和 rate 包的是两个不同的片段，从不重叠。**

官方原文（`me_0019`）：

```xml
Dickie left the shop without his moonflowers, indeed, but with
<rate factor="0.8">his Tinkler now whitely shining</rate>, and declared to be
&quot;<emo type="happy" level="2">real silver, and mind you take care of it</emo>, my lad,&quot;
his white cornelian seal carefully packed in a small cardboard box.
```

官方原文（`me_0021`，emo 在前）：

```xml
It was this observation that drew from Douglas—not immediately, but later in the
evening—a reply that had <emo type="sad" level="2">the interesting consequence
to which I call attention</emo>. Someone else told
<rate factor="1.25">a story not particularly effective</rate>, which I saw he was
not following.
```

**两条可直接照抄的规则：**

1. **emo 和 rate 分给不同的词/短语**，不嵌套、不共用一个 span（官方铁律 `Operations cannot nest or cross`）
2. **组合集只用 0.8 和 1.25 两个极端值**，不做精细调速 —— 说明在组合场景里 rate 的定位是「明显快一档 / 明显慢一档」，不是微调

⚠ 但**我们实测（见第九节）**：`emo` 和 `rate` 同时出现时，**rate 会被 emo 抑制**（纯 rate 0.88 → 17.76s，加 emo 后 → 16.32s，回到基线）。官方范式在文档层面成立，在这颗 GGUF 上不一定兑现，混用前必须单独验。

### 8.5.2 其余组合（同一数据集内）

| 组合 | 例数 | 组合 | 例数 |
|---|---|---|---|
| `emo` + `pause` | 30 | `emo` + `ins` / `sub` | 各 10 |
| `emo` + `pitch` | 15 | `del` + `emo` / `del` + `pause` | 各 10 |
| `emo` + `rate` | 15 | `ins` + `pause` / `pause` + `sub` | 各 10 |
| `pause` + `pitch` | 15 | 三/四标签组合 | 60 |

**`pause` + `rate` 有 15 例** ⇒ 我们之前「rate 不能和 pause 混用」是误判。

### 8.5.3 全库 rate 取值分布（451 次，双峰）

| 区间 | 次数 | 说明 |
|---|---|---|
| 0.67–0.70 | 2 | 极端慢，各 1 次 |
| **0.76–0.89** | **189** | 慢档主力，峰在 0.81（36） |
| 0.91–1.32 | 253 | 快档主力，峰在 1.25（34）、1.12（24）、1.20（23） |
| 1.70–1.99 | 9 | 极端快，极少 |

**双峰分布（慢峰 0.81 / 快峰 1.25）说明官方用的是「两档表演」，不是连续调速。**
这与我们的实测一致：rate 不是线性旋钮，只能表达「明显慢」和「明显快」。

### 8.6 xvector 的精确规则（README 原文）

> Edit speaker guidance defaults to `auto`: it is **disabled when the instruction contains at
> least one operation and every operation is `emo`, `bg`, or `enhance`**, and **enabled for
> text, pitch, rate, pause, speaker transfer, or mixed edits**.

源码对应：

```python
_KNOWN_CONTAINER_TAGS = {"del","ins","sub","emo","pitch","rate","enhance","bg"}
_AUTO_DISABLE_XVECTOR_TAGS = frozenset({"emo", "bg", "enhance"})
```

⇒ **emo / bg / enhance 关闭 speaker guidance（音色来自 voice_ref）；pitch / rate / pause / 文本编辑开启（音色来自 source_audio）。**
可以 `--use-xvector on` 强制开启。

### 8.7 官方自评：情绪是强项，副语言是弱项

README 的 EmergentTTS-Eval（对 gpt-4o-mini-tts 的胜率）：

| 模型 | Emotions | Paraling. | Quest. | Syntax |
|---|---|---|---|---|
| gpt-4o-mini-tts | 59.2% | 58.8% | 52.7% | 57.1% |
| **dots.tts (Pretrain)** | **72.7%** | 54.7% | 48.4% | 58.4% |
| dots.tts (SOAR) | 63.9% | 52.7% | 47.0% | **65.7%** |

**Emotions 72.7% 是所有开源模型里最高，但 Paraling（副语言：叹气/笑/耳语）和 Quest（疑问句）都低于 gpt-4o-mini-tts。**

对我们（睡前低语朗读）来说，这正好命中弱项。

---

## 九、★ 实测（第三批）：只有 emo 有效，而且必须强制开 xvector

### 9.1 tts 任务：pitch 完全无效（131 词）

基线 `MKT_L_plain.wav`：52.32s / 中位 F0 73.7 Hz / 131 词全对。

| 变体 | 时长 | 中位 F0 | Δ半音 |
|---|---|---|---|
| 词级 `<pitch, semitones=-6>hair</pitch>` | 52.96 | 74.5 | +0.18 |
| 词级 `<pitch, semitones=6>hair</pitch>` | 52.96 | 74.1 | +0.10 |
| 整段 `<pitch, semitones=-6>全段</pitch>` | 53.92 | 74.0 | +0.08 |
| `pitch -6` + `rate 0.70` 混用 | 57.12 | 73.1 | -0.14 |

整段降 6 半音应该让中位从 73.7 掉到 52 Hz，实测 **74.0（+0.08 半音）**。
**pitch 在 tts 任务下与 rate 一样，只是被「读到」了（时长有 ±2% 扰动），数值完全不执行。**

### 9.2 edit 任务：pitch 依然不兑现，但 emo 极强

短源 `ES_src.wav` = `c05.wav` 前 16.8s（42 词），`source_text == target_text`，
`max_tokens=420`（长源 55s 会 OOM，见第十三节）。基线中位 F0 73.3 Hz。

| 变体 | 时长 | 中位 F0 | Δ半音 | 声纹（锚=ES_src） |
|---|---|---|---|---|
| `ES_base` 无标签 | 16.16 | 74.9 | +0.38 | 0.9506 |
| 词级 `pitch -6` | 16.16 | 73.5 | +0.05 | 0.9622 |
| 整段 `pitch -6` | 16.16 | 68.4 | **-1.20** | 0.9330 |
| 整段 `pitch -12` | 16.16 | 72.1 | **-0.28** | 0.9273 |
| `emo angry L1` | 14.88 | 181.3 | **+15.67** | 0.3856 |
| `emo angry L2` | 14.56 | 182.3 | **+15.77** | 0.3404 |
| `emo angry L3` | 14.88 | 180.8 | **+15.63** | 0.3815 |
| **`emo angry L3` + `use_xvector=on`** | 17.12 | **205.9** | **+17.87** | **0.7654** |
| `enhance` | 16.16 | 74.0 | +0.16 | 0.9360 |

所有变体内容完整：**42/42 词**。

### 9.3 四条结论

**① pitch 是死参数。** 整段 -6 只降 1.2 半音（兑现 20%），-12 反而只降 0.28 半音（更小）。
不线性、不单调，等同于噪声。词级更是完全不动（+0.05）。

**② emo 是唯一真正生效的标签，效果极大。** `angry` 把中位 F0 从 74 拉到 181 Hz（+15.6 半音，
超过一个八度），时长缩短 8%。它是「换一种说法」，不是「微调」。

**③ `level` 是死参数。** L1/L2/L3 的 F0 分别是 181.3 / 182.3 / 180.8，**三档完全一样**。
只有 `type` 起作用。官方 data.md 写「Emotion levels are 1–3」，但模型不执行。

**④ 默认 emo 毁音色，强制 xvector 能救回来。**

| | 声纹 | F0 |
|---|---|---|
| `use_xvector=auto`（emo 自动关闭 guidance） | **0.38**（不像） | +15.6 半音 |
| `use_xvector=on`（强制开启） | **0.765**（同一人） | +17.9 半音 |

0.765 正是我们 tts 链路的正常水平（`L_plain` 对 `real_trim` 也是 0.765），
所以 **`emo` + `--use-xvector on` 是「情绪生效且音色不额外损失」的唯一组合**。

### 9.4 对生产链的意义

- **要改语气**：用 `emo` + `--use-xvector on`，按段落/场景打，不要指望 pitch/rate
- **要改语速**：`rate` 兑现率约 25%，只能当微调；大幅改速走后期 rubberband
- **不要用 `pitch`**：实测无效，白占标签位
- **`level` 可以随便填**，因为不起作用；但仍建议写 2 以贴合官方分布

---

## 十、★ 先选任务：edit 只复刻，tts 才生成

这是 2026-10-18 实测出来的、比所有标签规则都更底层的一条。

| | `--task tts`（无 source_audio） | `template_name=edit` + source_audio |
|---|---|---|
| 念什么 | `--text` 里的内容 | **`source_text`**（target_text 被忽略） |
| 长度上限 | 由文本与 max_tokens 决定 | **≈ source_audio 时长** |
| 131 词实测 | 52.32s / 131 词 / 相似 0.994 | 15.68s / **28 词** / 相似 0.158 |
| 音色（锚 real_trim） | 0.765–0.809 | 0.628（复刻短源） |
| 改内容 | 直接写文本 | **必须用 `<sub>` / `<ins>` / `<del>`** |

**证据链**：

1. 同一段 131 词文本，edit 任务（源 14.68s）输出 15.68s，ASR 念出来的是 `source_text`
   （P1 那 4 句），target 的 131 词一个字没念。相似度 0.158。
2. 同一段文本走 tts 任务：52.32s，131/131 词，相似 0.994。
3. `model_specs/dots_tts.json` 对 `source_text` 的说明：
   *"Optional source transcript override. If omitted, it is rendered from instruction tags."*
   —— 两个 override 字段都只是「覆盖从 instruction 渲染出来的结果」，模型真正吃的是 instruction。
4. 纯文本 instruction（无标签）不携带任何编辑意图 ⇒ 模型退化为「把 source 念一遍」。
5. 用 `<sub targ="新句">旧句</sub>` 后，edit 确实念出了新句 —— 但同时**丢掉了后面的
   `and a paper mache giraffe`**，并把逗号念成句号。

**结论**：

- **要生成新内容，一律用 `--task tts`**。整章链路（`chapter_run.py`）走的就是这条，是对的。
- **edit 任务只适合「同一段内容重念」**（source_text == target_text），
  这才是此前分块 edit 能到 0.91–0.95 的真实原因 —— 它不是「生成」，是「复刻」。
- 不要用 edit 做长内容生成：既受源时长限制，`<sub>` 又会丢词。

---

## 十一、实测结果（第一/二批）

### 第一批：短文本 29 词（P1 / 源 14.68s / max_tokens 600）

| 变体 | 格式 | span | pause | 时长 | ASR 词 | 相似度 |
|---|---|---|---|---|---|---|
| V_old_1 | 标准 | 1 | 无 | 17.12 | 29/29 | 0.991 |
| V_new_1 | 模型 | 1 | 无 | 16.96 | 29/29 | 0.980 |
| V_old_3 | 标准 | 3 | 无 | 16.96 | 29/29 | 0.991 |
| V_new_3 | 模型 | 3 | 无 | 16.64 | 28/29 | 0.982 |
| V_pause_old | 标准 | 3 | 有 | 17.12 | 28/29 | 0.982 |
| V_pause_new | 模型 | 3 | 有 | 19.04 | 28/29 | 0.982 |
| V_emo | 模型 | emo | 无 | 14.72 | 29/29 | 0.994 |

⚠ **这批实验有一半是无效的**：source_text = target_text = P1，无法区分模型念的是哪个字段。
所以「格式不影响正确性」这个结论虽然结论本身没错，但它的证据是循环的。
真正有效的是第二批。

### 第二批：长文本 131 词（c05 / tts 任务 / max_tokens 1200 / seed 42）

| 变体 | 标签 | 时长 | ASR 词 | 相似度 | 语音 wpm | 静音% | 间隙 n | 中位 | 音色 |
|---|---|---|---|---|---|---|---|---|---|
| L_plain | 无 | 52.32 | 131/131 | 0.994 | 202.1 | 25.6 | 24 | 0.46 | 0.765 |
| L_1 | 单 span 0.80 | 55.52 | 130/131 | 0.998 | 194.6 | 27.8 | 27 | 0.53 | 0.782 |
| L_9 | 9 span 0.72–0.90 | 61.44 | 131/131 | **1.000** | 185.2 | 30.9 | 26 | 0.61 | **0.809** |

### 结论一：多 span 不丢词

9 个 span、131 词，ASR 131/131，相似度 1.000。**「9 span 丢 1 子句」未能复现。**
短文本批次里丢的那个 `A`，是 3 span 的冠词吞并，不是整段跳词。

### 结论二：rate 不是线性旋钮，兑现率约 25%

总时长会被静音污染，必须拆开看**语音时长**（总时长 × (1 − 静音%)）：

| 变体 | 平均 rate | 理论语音 | 实测语音 | 兑现率 |
|---|---|---|---|---|
| L_plain | — | 38.90s | 38.90s | 基线 |
| L_1 | 0.80 | +25.0% | 40.10s（+3.1%） | **12%** |
| L_9 | 0.809 | +23.6% | 42.40s（+9.0%） | **38%** |

总时长的 +6.1% / +17.4% 里，**大头是静音变多**（25.6% → 27.8% → 30.9%），不是语音变慢。

真实块验证（rate 0.78，旧版单 span vs 新版 9 span）：

| 块 | 旧 raw | 新 raw | 变化 | 旧 wpm | 新 wpm |
|---|---|---|---|---|---|
| c01（130 词） | 60.32 | 64.00 | **+6.1%** | 129.3 | 120.9 |
| c02（131 词） | 60.96 | 60.32 | **−1.0%** | — | — |

**两块方向不一致**：一块慢 6.1%，一块反而快 1.0%，平均 +2.5%。
rate 0.78 理论应 +28%，实际连 5% 都不到。

⇒ **`<rate>` 不只是弱，还不稳定。** 不能用于控制语速。

⇒ **`<rate>` 是弱旋钮**：标称 0.78 实际只到 0.94 倍语速。
拆 span 有一点点帮助（12% → 38%），但远达不到标称值。
要真正大幅放慢，只能靠后期（rubberband / atempo），代价是音色下降。

### 结论三：rate 同时拉长停顿

静音占比：25.6% → 27.8% → 30.9%。间隙中位：0.46 → 0.53 → 0.61。
rate 不是单纯压语音，它把停顿也一起放大了。所以「用 rate 控语速」实际是「整体时间轴拉长」。

### 结论四：emo 方向与直觉相反

`<emo type="calm" level="2">` + `--use-xvector on`：14.72s，比无标签 17.12s **快 14%**。
calm ≠ 慢。情绪标签不能当语速用。

### 结论五：pause 会改变句法感知

`Dinosaur figurines, picture books, and a paper mache giraffe.`
→ 念成 `Dinosaur figurines. Picture books. And a paper mache giraffe.`
逗号列举被拆成三个独立句。pause 不是「加静音」，它改标点层级。

### 结论六：格式决定 pause 是否生效

无 pause 16.96s → 旧格式 pause 17.12s（+0.16s，废标签）→ 模型格式 19.04s（+2.08s）。
**pause 必须用模型格式（带 level）。**

---

## 十二、据此修订的规则

### 任务选择

1. **生成新内容用 `--task tts`**。edit 只复刻 `source_text`（输出长度≈源时长，`target_text` 被忽略）。
2. **要可控语速用 edit**：`tts` 下 rate 只兑现 2–6%，`edit` 下整段 rate 兑现 **84–93%** 且不丢词。

### 语速

3. **粒度反转**：`tts` 下单词 rate 有效、整段无效；`edit` 下整段有效、**单词完全无效**（时长声纹等同 base）。
4. **edit 套 rate 的代价是掉音色**：0.95 → 0.87（0.88x）→ 0.80（0.75x）。
5. **0.75 是安全下限**：0.60 要生成 27s，两次 OOM。
6. **语速的句法差异交给模型**，它自己有 2.3 倍波动（列举放慢、收尾加快）。

### 停顿

7. **pause 默认不进文本**，停顿走后期（`insert_pauses.py`），因为它会改标点层级（逗号被念成句号）。

### 情绪

8. **emo 是唯一真正生效的表达标签**（angry 让 F0 +15.6 半音），但：
   - **span 8–11 词最佳**，≥4 词，**≤11 词**（42 词整段声纹崩到 0.38）
   - **不要只包 1 个词**，会插 0.1s 高频假声
   - **必须 `--use-xvector on`**，否则音色整体切到 8s 的 voice_ref
   - **`level` 永远写 2**，1/3 无梯度
9. **emo 与 rate 互斥**：加 emo 后 rate 失效（17.76s → 16.32s）。要两者都要走 sequential。

### 放弃项

10. **`<pitch>` 彻底放弃**：两种任务下都无效（-6 降 1.2 半音，-12 只降 0.28，不线性不单调）。

---

## 十三、作废声明

| 旧结论 | 现状 |
|---|---|
| 9 个 span 丢 1 个子句 / 11 span 丢 2 | **未复现**（131 词 9 span，131/131） |
| 叠 ≥2 个 pause 整段跳词（38 词剩 10 词） | **未复现** |
| rate 与 pause 混用跳词 | **未复现** |
| rate 兑现率随文本变长稀释 | **成立**，且是硬限制（约 25%，拆 span 仅到 38%） |
| 标准 XML 格式是丢词根因 | **不成立**，格式只影响 pause 是否生效 |
| edit 任务能生成新内容 | **不成立**，只复刻 source_text |
| 分块 edit 音色 0.91–0.95 说明链路强 | **需重新解释**：那是同内容复刻，不是生成 |

---

## 十四、环境坑

- **连续跑 edit 任务会 OOM**：`failed to allocate DotTTS SOAR DiT cache memory`（629MB）。
  实测连续 2 组成功后，第 3 组开始必失败。组间至少 `sleep 20`，或每 2 组重启一次。
- **tts 任务同样要串行**，组间留间隔。
- `G:/Python310` 的 `python310._pth` 会让脚本目录不进 `sys.path`，
  脚本内需 `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`。

---

## 十五、改动记录

- 2026-10-18 上午：新建本文件 + `dots_markup.py`；`dots_prosody.py`、`chapter_run.py`
  改为经 `MK` 构造标签，输出模型格式。
- 2026-10-18 上午（第一批实测）：7 组短文本对照，修订 pause 策略与 span 合并。
- 2026-10-18 傍晚（第四批实测）：句中位置（句首/句中/句尾）+ 同句双情绪 + sequential 合成，
  结论：emo 严格局部、三处都生效、范围近似线性；sequential 的 rate 兑现 67% 但 emo 只剩 20%，
  不推荐（改单步 emo + 后期 rubberband）。手册 3.2/3.3/8.3 与禁令 13 已同步。
- 2026-10-18 下午（第三批实测）：官方词句表演规范 + 9 组 pitch/emo/enhance 对照，
  **新增第八节「官方怎么表达语气语调」**；结论：pitch 是死参数、emo 唯一有效但须强制 xvector、
  level 无梯度。
- 2026-10-18 中午（第二批实测）：131 词长文本 + 任务对照，**新增第七节「先选任务」**，
  确认 edit 只复刻、tts 才生成；多 span 不丢词（上限 10）；
  rate 兑现率约 25%（非标称值）；旧「丢词」结论作废。
- 2026-10-18 傍晚（全库核查）：统计 doteBench 全部 1,152 例，**8.5 节重写为「数据集严格分离」**
  —— emotion 集 612 例含 rate **0 次**、prosody 集 360 例含 emo **0 次**；
  新增 8.5.1（官方 emo+rate 唯一范式：分片段、rate 只取 0.8/1.25）、
  8.5.3（全库 rate 双峰分布，慢峰 0.81 / 快峰 1.25）。
  `dots_markup.py` 新增 `RATE_COMBO_VALUES`，`validate()` 增加「emo 与 rate 同块」与
  「组合场景 rate 不在官方档位」两条告警（兼容模型格式与标准 XML 两种写法）。
