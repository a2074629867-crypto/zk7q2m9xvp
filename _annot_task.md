# 停顿语义标注任务（三方交叉验证）

## 背景

我们在做 TTS 配音的韵律控制。从真人母带（马修睡前朗读，1615s）实测得出：
停顿时长能被「句间/句内」和「前后语音段总长」解释 **47.6%**（R²），剩下 52% 必须靠语义判断。

这一步要标注的就是那 52%：**每处标点位置，该不该停、停多长**。
标注结果会成为 `pause_llm.json` 的新版本，直接驱动后期插停顿（`mt_final.sh`）。

角色是**夏尔（Charles）**，一个情绪化的男孩，在对白里跟 Edmund（成年人）争一间房子。
所以判据是**对话的表演逻辑**，不是朗读的语法逻辑。

---

## 标注项

对每条台词，输出三个字段：`kind`（每处标点一个）、`sentence_type`、`focus`。

### 一、kind —— 每处标点位置的停顿类型

标在**标点之后**。逗号、句号、问号都要标。

| kind | 时长 | 判据（满足任一） |
|---|---|---|
| `drop` | **0** | ① 语法性逗号：`like,` `as,` `than,` `that,` 前后是同一语法单元<br>② 填充词/呼语后紧接主句：`Well, it was...` `Look, then,...` `Anyway,...`<br>③ 反意疑问的逗号：`..., will it?` `..., can she?` `..., then?`<br>④ 连续短项列举（一个词一个逗号）：`a, b, c` |
| `tight` | **0.15~0.25s** | ① 插入语/补充说明：`He's old, I told you.`<br>② 从句没说完，后面还有主句成分<br>③ 抢话、追问的紧接 |
| `clause` | **0.43~0.55s** | ① 两个完整分句之间（各有主谓）<br>② 句号后接新句子，但还在同一段对话里 |
| `beat` | **0.60~0.76s** | ① 说完一句重话，等对方反应<br>② 信息揭示、递出东西<br>③ 把话压给对方<br>④ 转折前蓄势 |

**上限提醒**：夏尔真人实测停顿最大 0.76s，超过这个值不是他的说话方式。

**判定顺序**（重要，否则会互相覆盖）：
1. 先看**是不是不该停**（drop）—— 语法性/填充词/反意疑问
2. 再看**是不是只是半拍**（tight）—— 插入语/从句未完/抢话
3. 再看**是不是情绪落点**（beat）—— 说完重话要对方接
4. 剩下都是 `clause`

**反例**（容易标错）：
- `Well, it was in somebody's house.` → `Well,` 是 `drop`，不是 `tight`。填充词黏在主句上。
- `He's old, I told you.` → `old,` 是 `tight`，不是 `clause`。`I told you` 是插入语。
- `It is my house, it is private.` → `house,` 是 `clause`。两个都是完整分句，而且他在宣示。
- `Downstairs is something very valuable. Something you've never seen.` → 句号是 `beat`。他在递信息，等对方反应。

### 二、sentence_type —— 整条台词的句型

看**最后一句**的句末标点与结构：

| 值 | 判据 |
|---|---|
| `stmt` | 陈述句，句末 `.` |
| `wh` | wh- 疑问：`what/why/where/who/how/when/which` **出现在句首 2 个词内**，句末 `?` |
| `yesno` | 一般疑问：助动词/be 开头，句末 `?` |
| `tag` | 反意疑问：句末是 `..., isn't it?` `..., can she?` `..., shouldn't he?` |
| `echo` | 回声问：重复对方刚说的话，≤3 词，句末 `?` |

**判定顺序不能反**：`wh` 优先。`Oh, what is it?` 的尾部 `is it` 长得像反意疑问，但它是 wh- 句。

### 三、focus —— 焦点词

**这一条台词里，说话人最想让对方听见的那一个词。** 原词照抄，不改编、不改大小写。

判据：
- 对白里通常落在**指责点 / 否认点 / 炫耀点**上
- 是那个「如果听漏了，整句话的意思就变了」的词
- 一般 1 个，最多 2 个（用 `+` 连）

例：`It is my house, it is private.` → focus = `my`（争的就是归属）
例：`You're a liar.` → focus = `liar`

---

## 输出格式

严格输出 JSON，不要解释、不要 markdown 代码块：

```json
{
  "L058": {
    "sentence_type": "wh",
    "focus": "then",
    "kind": [
      {"after": "What", "punct": "?", "kind": "clause", "why": "整条只有一个问句，句末收束"}
    ]
  }
}
```

`after` 填标点前那个词的原词。`why` 一句中文，不超过 25 字。

---

## 待标样本（16 条）

每条给出：key、说话人、情绪、原文。

```
L058  C calm        What then?
L078  C sad         No. But...
L090  C calm        In Wales.
L033  E calm        That's years ago.
L062  E calm        Your own flat?
L053  E happy       Why have you come here?
L050  C surprised   Oh, what is it? What have you found?
L063  C calm        Yes. No. Well, it was in somebody's house.
L066  E calm        Why didn't your father buy a proper house?
I03   C -           It was not his house. Nothing here was his.
L011  E calm        I wouldn't do any harm. Why can't I go?
L057  E calm        Downstairs is something very valuable. Something you've never seen.
L046  E happy       It is my house, it is private. I got here first. Nobody should come here.
L079  E happy       I don't believe you. You're a liar. The Battle of Britain was in the war.
L068  C sad         Well, my mother can't afford to buy us a house, can she? We can't help that.
L069  E calm        Your father should have left you some money, then, shouldn't he? Didn't he have any?
```

---

## 场景背景（用于判断情绪落点）

夏尔（C，约 10 岁男孩）和 Edmund（E，成年男性）在一座空房子里对峙。
夏尔认为自己拥有这房子（"It's my house"），Edmund 在盘问他、质疑他的说法。
夏尔处于**防守+宣示**的位置：他要证明自己有理，同时怕被赶走。
Edmund 处于**审问+轻蔑**的位置：他在试探、在戳穿。

所以夏尔的停顿往往落在「我要你听清楚这一点」的地方（beat），
Edmund 的停顿往往落在「你答不上来了吧」的地方（beat）或「随口一提」（tight）。
