# dots.tts 官方 emo 示范与规范

> 全部内容来自本地 doteBench V1.0（`G:/_setup/doteBench`）的 emotion 数据集 612 例
> + 官方 parser 源码 + candidate 适配器源码，非推测。
> 配套实测见 `DOTS_MARKUP_RULES.md` 第九节。

---

## 一、官方示范：同一段音频的三种写法

这是官方最漂亮的设计。**同一条源音频（sha256 `e5f60b48…`）、同一段文本**，只改 emo 的作用范围：

### 1.1 `_whole` —— 整段包住

```xml
<emo type="angry" level="2">I can hear something scraping against the floorboards
just outside my bedroom door and the lights have suddenly flickered out leaving me
completely alone in the freezing darkness of this empty house tonight.</emo>
```

### 1.2 `_phrase` —— 只包中间一个短语

```xml
I can hear something scraping against the floorboards just outside my bedroom door
and <emo type="melancholic" level="2">the lights have suddenly flickered out</emo>
leaving me completely alone in the freezing darkness of this empty house tonight.
```

### 1.3 `_multi` —— 一句里两个不同情绪

```xml
I can hear something <emo type="happy" level="2">scraping against the floorboards
just outside my bedroom door</emo> and the lights have suddenly flickered out
<emo type="disgusted" level="2">leaving me completely alone in the freezing
darkness</emo> of this empty house tonight.
```

三条共同点：

1. **标签内只有文字，没有其他标签**（`Operations cannot nest or cross`）
2. **span 边界落在语法成分上**：`the lights have suddenly flickered out` 是一个从句，
   `those heavy footsteps creeping closer through the shadows behind the locked door` 是一个名词短语
3. **`type` 与 `level` 永远同时出现**

### 1.4 更短的 `_multi` 示例

```xml
There was <emo type="afraid" level="2">nothing behind him except for</emo>
his bookcase which <emo type="surprised" level="2">seemed to be missing</emo>
a single, important book.
```

```xml
Unlike VoiceCode, which <emo type="calm" level="2">is a complete solution</emo>,
Dragonfly is just <emo type="happy" level="2">an improved Python API</emo> to Dragon.
```

注意第二个例子里 `calm` 和 `happy` **都是正向**——不是随便乱标。
（`intense` 集确实有语义不匹配的情况，因为它是「改情绪」任务；`neutral` 集是「从无到有」，情绪更贴合语义。）

---

## 二、官方的量化分布

### 2.1 数据集构成

| split | 例数 | whole | phrase | multi | 源情绪 |
|---|---|---|---|---|---|
| `intense` | 300 | 100 | 100 | 100 | `afraid`（全部） |
| `neutral` | 312 | 104 | 104 | 104 | 无（本来就是中性朗读） |

**`intense` = 改情绪**（怕 → 怒/悲/厌/惊/喜）；**`neutral` = 从无到有**。

我们生产链的源音频是平静朗读，**对应 `neutral` 场景**。

### 2.2 情绪枚举：parser 允许 9 种，样例出现 8 种

`doteBench/src/dotebench/instructions/parser.py:18`：

```python
EMOTIONS = {
    "angry", "happy", "sad", "afraid", "disgusted",
    "surprised", "calm", "melancholic", "neutral",
}
```

样例分布（624 个 span）：

| intense | 次数 | neutral | 次数 |
|---|---|---|---|
| disgusted | 58 | surprised | 52 |
| angry | 57 | afraid | 52 |
| melancholic | 57 | disgusted | 52 |
| happy | 57 | calm | 52 |
| sad | 57 | happy | 52 |
| surprised | 57 | sad | 52 |
| afraid | 57 | melancholic | 52 |
| — | — | angry | 52 |

**`neutral` 在 624 例里一次都没出现**，但 parser 接受。作为「取消情绪」用可能有效，未实测。

### 2.3 `level`：624 例全部是 2

```
intense: {'2': 400}      # 0 个 1，0 个 3
neutral: {'2': 416}      # 0 个 1，0 个 3
```

parser 接受 1/2/3（`attrs["level"] not in {"1","2","3"}` 才报错），
但**训练数据里只有 2**。这解释了我们实测的「L1/L2/L3 的 F0 完全一致（181.3 / 182.3 / 180.8）」——
模型没见过 1 和 3，所以它对强度没有梯度。

⇒ **level 永远写 2，不要指望它调强度。**

### 2.4 span 长度：一段完整从句，**不是逐词**

> ⚠ 此前本文件写「phrase 中位 2–3 词」，是统计错误：数据集**中英各半**，
> 中文用 `split()` 会把整句算成「1 词」，把中位数拉低。以下为按语言分开重算的结果。

| 语种 | 形式 | 中位 | 区间 | 单词占比 |
|---|---|---|---|---|
| 英文 | `_phrase` | **8 词** | 5–12 | **0%** |
| 英文 | `_multi`（每段） | **6–7 词** | 4–11 | **0%** |
| 英文 | `_whole` | 28–33 词 | 16–44 | 0% |
| 中文 | `_phrase` | **11–13 字** | 6–20 | **0%** |
| 中文 | `_multi`（每段） | **7–11 字** | 6–17 | **0%** |
| 中文 | `_whole` | 30–46 字 | 24–48 | 0% |

**结论：官方 emo 一律包「一个语法完整的从句」，最典型是 6–12 词。**
没有一个是单个词，也没有「逐词各打一个 emo」的用法。

**单词级的标签是 `rate` / `pitch`（prosody 集 30% 是 single_word），不是 `emo`。** 两者别混。

原文（英文 `_phrase`，6 / 8 / 12 词）：

```xml
I can hear something scraping against the floorboards just outside my bedroom door
and <emo type="melancholic" level="2">the lights have suddenly flickered out</emo>
leaving me completely alone in the freezing darkness of this empty house tonight.

Please stay back and do not come any closer because <emo type="disgusted" level="2">I
can hear your breathing in the shadows</emo> and I have nowhere left to run.

I can hear <emo type="happy" level="2">those heavy footsteps creeping closer through
the shadows behind the locked door</emo>, and I have absolutely nowhere left to hide.
```

⇒ **与本项目实测完全吻合**：我们独立测出「8–11 词最自然」，官方 phrase 中位正是 8 词。


### 2.5 span 位置：几乎不在句首/句尾

| | 句首 | 句中 | 句尾 |
|---|---|---|---|
| intense | 107 | 292 | 1 |
| neutral | 104 | 312 | 0 |

（句首那 107 / 104 全部来自 `_whole`，因为整段就是全文。真正的 phrase 全部在句中。）

### 2.6 span 边界：`and` 是主战场

span 前一个词 / 后一个词的 top：

| | 前一个词 | 后一个词 |
|---|---|---|
| intense | and 19、that 12、because 8、like 6 | and 30、leaving 10、that 9、in 7 |
| neutral | and 14、the 8、was 6、of 6 | and 35、to 11、of 9、that 7 |

**官方在连词处切**，和我们「马修停顿由标点驱动」的结论方向一致——语法边界就是情绪边界。

---

## 三、官方 parser 的硬约束（写错直接报错）

`parser.py:58`：

```python
if kind not in ATTRS or set(attrs) != ATTRS[kind] or len(node):
    raise ValueError(f"Unsupported tag, attributes, or nesting: {kind}")
```

`ATTRS = {"emo": {"type", "level"}, ...}`

⇒ 三条硬规则：

1. **`type` 和 `level` 必须同时存在**，少一个就报错。只写 `<emo type="sad">` 是非法的。
2. **不能有多余属性**（例如 `<emo type="sad" level="2" desc="...">` 非法）。
3. **不能嵌套**（`len(node)` 必须为 0）。

另外 `EMOTIONS` 之外的 type 直接报错，所以拼写必须精确。

---

## 四、官方 runtime 实际收到什么

### 4.1 `source_text == target_text`（emo 不改文字）

`parser.py:75-78`：

```python
source = "" if kind in {"ins", "pause"} else body
target = "" if kind in {"del", "pause"} else attrs["targ"] if kind == "sub" else body
```

emo 走 `else body` 分支 ⇒ **source 和 target 都是 body**，完全相同。

`compile.py:31-36`：

```python
return {
    "instruction": model_instruction(request.instruction_xml),
    "source_text": parsed.source_text,
    "target_text": parsed.target_text,
    **options,
}
```

⇒ 官方调 emo 时，`source_text` 和 `target_text` 都是**剥掉所有标签的纯文本**，
`instruction` 保留 emo 标签。**emo 是纯声学操作，不改任何字符。**

### 4.2 `[EN]` / `[ZH]` 前缀（我们一直没加）

`compile.py:47-50`：

```python
prefix = {"en": "[EN]", "zh": "[ZH]"}[request.language]
for key in ("source_text", "target_text"):
    text = compiled[key].strip()
    compiled[key] = text if not text or text.startswith(prefix) else prefix + text
```

官方喂给 public runtime 的 source/target **都带语言前缀**。
我们此前所有实验都没加这个 token。

### 4.3 `emo` 标签本身不做格式转换

`compile.py:25-26` 只转换 `pitch` / `rate` / `pause`：

```python
native = re.sub(r"<(pitch|rate)\b[^>]*>", prosody, instruction_xml)
return re.sub(r"<pause\b[^>]*>", pause, native)
```

⇒ `<emo type="x" level="2">` **原样进入模型**，和标准 XML 一致。
这是 emo 一直正常工作的原因（不像 rate 需要逗号格式）。

### 4.4 多情绪必须分步：`sequential`

`planner.py::plan_operations` 文档字符串：

```
Execute text tags first, then acoustic tags, preserving each XML order.
```

- 只有一个操作 → 直接一次调用
- 多个操作 → **每个操作单独一步**，上一步输出作为下一步的 source
- 顺序：`sub/ins/del` 先全部执行，然后 `emo/pitch/rate/pause`

⇒ `_multi`（两个 emo）用 sequential 是 **2 次生成**，音色会累积漂移。
`one_take` 一次调用带两个 emo 也支持，但我们的实测显示多 span 会影响稳定性。

---

## 五、对照我们的实测（同一套标签，差别很大）

固定条件：短源 `ES_src.wav`（16.8s / 42 词）、`source_text == target_text`、seed 42、max_tokens 420。

| 范围 | 词数 | 时长 | 声纹（锚=源） | 听感 |
|---|---|---|---|---|
| 无标签 | — | 16.16s | **0.9506** | 正常 |
| **1 词 emo** | 1 | 16.32s | 0.9327 | 词后插 0.11s 假声，像吸气 |
| 短语 emo | 6 | 16.16s | 0.8780 | 局部 0.77s 连续改动 |
| 从句 emo | 6 | 17.12s | 0.9021 | 该段变慢 |
| **整句 emo** | 11 | 17.12s | **0.8858** | 整句慢 6%，最像正常表演 |
| 两词两情绪 | 2 | 16.16s | 0.9389 | 两处各一小段 |
| **整段 emo** | 42 | 14.88s | **0.3815 崩** | 整体换声，不是马修 |

### 三条铁律

1. **官方用 6–12 词（英文中位 8），我们实测最自然也是 8–11 词 —— 两边一致。**
   1 词会插假声（官方 0 例），2–3 词像局部音效（官方 0 例）。
2. **上限 11 词**。超过就整段切到 voice_ref（8s 参考撑不住），声纹 0.95 → 0.38。
3. **`--use-xvector on` 能救音色**：整段 emo + 强制开启，声纹从 0.38 回到 0.77，
   而且情绪更强（F0 +17.87 半音 vs +15.63）。

---

## 六、给本项目的 emo 标注规则

### 6.1 写法

```xml
<emo type="sad" level="2">被情绪覆盖的那一段文字</emo>
```

- `type` 从 9 种里选，拼写精确
- `level` **固定 2**
- 不嵌套任何其他标签
- span **落在从句或短语边界**，优先在 `and` / `that` / `because` 处切
- span **8–11 词最佳**，最少 4 词（低于 4 词会插假声），最多 11 词

### 6.2 生成参数

必须加：

```
--request-option use_xvector=on
```

否则只要指令里全是 emo，官方规则会自动关闭 speaker guidance，音色整体崩掉。

### 6.3 不要做的事

| 做法 | 后果 |
|---|---|
| 整段包 emo（>11 词） | 音色崩到 0.38 |
| 只包 1 个词 | 该词后插 0.1s 高频假声 |
| 写 `level="3"` 想加强 | 无任何效果（模型只见过 2） |
| 用 `<pitch>` 配合 | pitch 在两种任务下都无效 |
| emo + rate 同时打 | rate 被 emo 抑制（纯 rate 17.76s → 加 emo 后 16.32s） |

### 6.4 与语速的关系（官方 vs 我们）

#### 官方怎么放：emo 与 rate 分片段，从不重叠

查 doteBench 全库 1,152 例：

| 数据集 | 例数 | 含 rate | 含 emo |
|---|---|---|---|
| `emotion/intense` | 300 | **0** | 300 |
| `emotion/neutral` | 312 | **0** | 312 |
| `prosody/default` | 360 | 240 | **0** |
| `compositional/default` | 240 | 69 | 138 |

**官方 emo 示范里一个 rate 都没有。** 两者只在组合集里共存，共 33 例，特征是：

- rate **只取两个值**：`0.8`（17 次）/ `1.25`（16 次）
- emo span 词数中位 1，rate span 词数中位 1
- **各包不同的片段**，不嵌套、不共用

官方原文（`me_0019`）：

```xml
... but with <rate factor="0.8">his Tinkler now whitely shining</rate>, and
declared to be &quot;<emo type="happy" level="2">real silver, and mind you take
care of it</emo>, my lad,&quot; ...
```

⇒ 官方的语义是：**「这个词说慢一点」+「这句话带点高兴」**，两件事分给两处，互不干扰。

#### 我们实测：混用会互相抑制

| 变体 | 时长 | 结果 |
|---|---|---|
| 纯 `rate 0.88` | 17.76s | 兑现 84% |
| `emo` + `rate 0.88` | 16.32s | **rate 失效，回到基线** |

⇒ 在这颗 GGUF 上，**同一个块里语速和情绪只能二选一**。要两者都要，走 sequential：
先生成 emo 版，再对结果套 rate（每步一次生成，音色会累积漂移）。

⚠ 这条是「官方范式可行、我们引擎不兑现」的典型例子。照抄官方写法之前必须单独验。

---

## 七、文件位置

| 内容 | 路径 |
|---|---|
| 官方 emotion 数据集 | `G:/_setup/doteBench/data/emotion/{intense,neutral}/manifest.json` |
| 官方 parser（校验规则） | `G:/_setup/doteBench/src/dotebench/instructions/parser.py` |
| 官方标签转换 | `G:/_setup/doteBench/src/dotebench/candidates/dots_tts_edit/compile.py` |
| 官方分步规划 | `G:/_setup/doteBench/src/dotebench/compilers/sequential/planner.py` |
| 本地标记模块 | `G:/_setup/dots_markup.py`（`EMO_TYPES` 已补 neutral） |
| 本项实测报告 | `G:/_setup/dots_word_emo.html` |
