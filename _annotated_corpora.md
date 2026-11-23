# 带标注的真人语料库清单（2026-11-01 核查）

> 目的：不自己标注，直接拿别人标好的标签来驱动选角 / 档位 / 停顿 / 重音。
> 判定口径只看三件事：① 标签字段是什么 ② 能不能真的下到手 ③ 许可。
> 已知前提：不追商业可用（个人自用），所以 CC-NC 全部可接受，但**仍需绕开 LDC 付费墙**。

---

## 一、主表（按标注维度分五类）

| # | 库 | 标注维度 | 规模 | 获取 | 许可 | 喂我们哪一层 |
|---|---|---|---|---|---|---|
| 1 | **Expresso** (Meta, IS2023) | 26 种**表演风格**逐条标注（含 whisper / sarcastic / enunciated / sympathetic / child_directed / sleepy / bored / projected）；read 部分另有 **asterisk 对比重音**标注 | 47h / 4 speakers（2男2女，成人）/ 48kHz/24bit / 录音棚 | 官方走 textlesslib 签协议；HF 有第三方镜像但**只有 read config** | CC-BY-NC 4.0 | L1b 档位（最贴） |
| 2 | **EARS** (Meta/UHH, IS2024) | 7 种朗读风格（regular/loud/whisper/high pitch/low pitch/fast/slow）+ **22 种情绪** + 18min/speaker 自由独白；`speaker_statistics.json` 给**年龄 18–75、性别、族裔、母语、身高体重** | 100h / 107 speakers / 48kHz / **全消声室** | GitHub releases，`curl` 直下 p001–p107 | CC-NC 4.0 | L1a 选角 + L1b 档位 |
| 3 | **GLOBE** (2024) | `age` 字段（teens / twenties / thirties …）+ `accent`（164 种）+ `gender` + `speaker_id` + 转写 | 535h / **23,519 speakers** / 24kHz | HF `MushanW/GLOBE`，47.6GB | **CC0** | L1a 选角（青少年男声唯一易得来源） |
| 4 | **MyST** (My Science Tutor) | 儿童会话语音，3/4/5 年级（约 8–11 岁），230K utterances 中 100K 有转写 | ~400h / 1.3K students / 10.5K sessions | myst.cemantix.org（CC 非商用）+ LDC2021S05 | CC-BY-NC | L1a（真儿童，Charles/Fielding） |
| 5 | **CSLU Kids** v1.1 | 幼儿园–10 年级，**逐年段**标注；含 spontaneous 独白 ~1min/人 | 1100 children / 1017 files / 16kHz | **LDC 付费**（LDC2007S18） | CSLU Agreement | L1a（年龄梯度最细） |
| 6 | **DisfluencySpeech** (2024) | **逐类不流畅标注**：filled pauses / explicit editing terms / discourse markers / coordinating conjunctions / asides / restarts / false starts / 笑声 / 叹气；另给**三档转写**（A 全量、B 去填充词、C 去 false start）+ MFA 对齐资源 | ~10h / **单人** / 录音棚 / 5,000 条 | HF `amaai-lab/DisfluencySpeech`，1.48GB 直下 | 开放（CC-BY-4.0） | **L3 停顿（最贴）** |
| 7 | **PodcastFillers** (Adobe, IS2022) | 填充词 uh/um **带时间戳** + 50K 非填充事件（呼吸/笑/重复词/噪声）；199 集播客 | 145h / 350+ speakers / 44.1kHz | Zenodo 7121457 | 非商用研究 | L3 停顿（找词点） |
| 8 | **NXT Switchboard** | **ToBI 韵律标注**（音高重音 / break index 0–4）+ **contrast 标注** + 音节/音素级 | 76 对话带 ToBI | LDC（Switchboard 本体付费） | LDC | **L6 重音（最贴）** |
| 9 | **BURNC** (Boston U Radio News) | **人工 ToBI**：pitch accent 五型 → 二值 prominence（音节级 34.3% prominent / 词级 54.2%）+ break index + POS | 7 speakers（6 人有标注，~3h） | 需向 BU 申请 | 研究用 | L6 重音（人工金标） |
| 10 | **Helsinki Prosody Corpus (HPC)** | **词级 prominence 二值标签**，自动标注但覆盖全量 | LibriTTS clean **262.5h / 1230 speakers** | 公开（Helsinki 组） | 开放 | **L6 重音（规模最大）** |
| 11 | **MELD** (ACL2019) | **角色名 speaker** + 7 情绪 + 极性 + 对话 ID/轮次 + **起止时间戳**；1,400 对话 / 13,000 utterances，avg 3.59s | Friends 剧集 | HF `declare-lab/MELD` 直下 | 研究用 | 对白结构 + 情绪 |
| 12 | **CREMA-D** | 6 情绪 + **情绪强度**（low/med/high/high+unresolved） | 7,442 clips / 91 actors | GitHub 直下 | 开放 | L1b 强度维度 |

---

## 二、三个"标签体系本身也是资产"的点

不是数据，是**别人已经定好的标注规范**，可以直接拿来当我们验收判据的骨架：

1. **Switchboard 五类不流畅标注**（`{F...}` filled pause / `{E...}` editing term / `{D...}` discourse marker / `{C...}` conjunction / `{A...}` aside，外加 `[...+...]` restart、`;...;` 非语音事件）
   → 我们的"找词点"目前只按"最长静音 ≥1.20s"判，粗。这五类可以细化成五个可分别测量的位置。
2. **ToBI break index 0–4**（0 粘连 / 3 中间短语 / 4 句调短语边界）
   → 我们的双标尺停顿只有"句内 0.55–0.70 / 找词 1.2–1.4 / 句末 0.9–1.1"三档，缺"粘连"这一档（0 级），而 `ago, either` 那种不清停正是 break 0。
3. **Prominence 二值化做法**（BURNC 把 H*/L*/L*+H 全并成"prominent"）
   → 正是我们 `rel_z` 想做的事。BURNC 的 34.3%/音节、54.2%/词 给了我们一个**真人基准比例**，可用来校验我们文档里 "+1.19 / 噪底 +1.47" 的口径。

---

## 三、硬缺口（没有任何公开库同时满足）

| 需求 | 有标注的库 | 缺什么 |
|---|---|---|
| 儿童 + 情绪 | 无 | MyST/CSLU 只有转写没有情绪；EARS/Expresso 全是成人 |
| 儿童 + 停顿 | 无 | DisfluencySpeech/PodcastFillers 全是成人 |
| 男孩 12–13 岁 + 表演 | 无 | GLOBE 有 `teens` 但是 CC0 众包朗读，不是表演；Expresso 的 `child` 风格是**成人模仿儿童**（0.4h） |
| 中文 + 上述任一 | 基本无 | 本清单全部英文 |

→ 结论：**Charles / Fielding 这条线必须自己采**（就是 `_corpus_plan.md` 的 C 路），其余四类可以全部靠现成标注库。

---

## 四、立即可下的三条命令（全部落 G 盘，不碰 C 盘）

```bash
# 1) 不流畅标注（最贴 L3，1.48GB）
export HF_ENDPOINT=https://hf-mirror.com
python -c "from datasets import load_dataset; \
d=load_dataset('amaai-lab/DisfluencySpeech', cache_dir='G:/voice_lib/raw/hf'); print(d)"

# 2) 青少年/年龄/口音元数据（47.6GB，先只取 metadata 不取音频）
python -c "from datasets import load_dataset; \
d=load_dataset('MushanW/GLOBE', split='train', streaming=True); \
import itertools,json; print([r for r in itertools.islice(d,3)])"

# 3) 对白结构 + 情绪（MELD，仅 CSV 部分，几百 KB）
curl -L https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/train_sent_emo.csv \
  -o G:/voice_lib/raw/meld_train.csv
```

EARS 需逐个 speaker 下（每个 ~1GB），建议先只下 3–5 个**年龄落在 20–30 且性别男**的：
```bash
curl -L https://github.com/facebookresearch/ears_dataset/releases/download/dataset/p001.zip -o p001.zip
```
先看 `speaker_statistics.json` 挑人，再下音频。

---

## 五、优先级建议（按"能立刻改善交付"排序）

1. **DisfluencySpeech**（10h，单人，直下）→ 只用来**校准停顿双标尺**：它是真人读出来的自然不流畅，标了每一类的位置，可以直接量出"真人找词点有多长、多久出现一次"，替掉我们现在的经验值 1.2–1.4/≤15%。
2. **HPC**（262.5h 词级 prominence）→ 直接回答"副词到底该不该重读"，用 1230 人的分布做基准，而不是靠我们 55 条副词的小样本。
3. **Expresso**（26 风格）→ 用作**档位命名与边界**的参照：我们的"L1b 档位"目前是自造词，Expresso 的 26 个词是同行共识，且带平行朗读（同一句 7 种风格）＝天然的档位对照实验。
4. **GLOBE / EARS metadata** → 只取元数据，先算出"我们能从公开库里凑出多少个 12–13 岁男声候选"，如果为 0 就死心自己采。

---

## 六、明确不采用的

- **LDC 付费库**（CSLU Kids / Switchboard 本体 / MyST-LDC 版）：不是买不起，是要走机构协议，个人拿不到。
- **仅文本标注、无音频的库**（EmotionLines 纯文本版）：对我们零价值。
- **非英语库**（ESD 中文部分、CORAA 葡语）：跨语言克隆虽可行，但停顿与重音的统计量不可迁移（第 8 次分母塌陷的教训）。
