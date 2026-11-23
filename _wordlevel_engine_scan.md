# 词级声学属性引擎选型（2026-11-12 15:0x）

> 需求原话：**「找一个比 WordVoice 更好用的、预测每个词声学属性的引擎，来辅助挑选好的 seed，以及筛出大部分韵律没读到、有错误的」**
> 验证口径：本机已装并跑过 = 已验；只读到论文/README = 未实测；二手博客 = 二手。

---

## 0. 先纠一个定性错误（上一轮我把 WordVoice 归错类了）

**WordVoice = 控制器，不是分析器。**

- 它的词级 5 维（duration / boundary / energy / pitch / tone）是**生成时的输入条件**，不是从已有音频里读出来的属性。
- 要拿它的「预测」，必须先让它**合成**：bound-token 做 acoustic planning → 再 token-to-waveform 调制。
- 我们的场景是「已有 2 个 take，挑哪个好」——这是**判分**，不是生成。

⇒ 所以「比 WordVoice 更好用的预测引擎」这个问法本身要去掉 WordVoice 这个锚：它不在同一个赛道上。真正要换的是**工具类别**：从「可控 TTS」换成「词级属性提取 + reference-free 判分」。

---

## 1. 两个用途其实需要三种不同的东西（没有单个引擎能全包）

| 你要的 | 本质问题 | 不能用什么 | 应该用什么 |
|---|---|---|---|
| 筛「韵律没读到 / 塌成单模式」 | 应然 vs 实然的**局部**偏差 | 句级 MOS（UTMOS/DNSMOS）、分布级（TTSDS2） | 词级属性表 + reference-free 韵律似然 |
| 筛「有错误」（吞字/读错） | 音素级发音偏差 | 任何声学预测器（它们不管对错） | ASR 词级置信 / GOP |
| 挑 seed（2 选 1） | **排序**，不是绝对值 | 绝对阈值类指标 | 同句双 take 互为参考 + 批次中位数 |

**最关键的一句**：文本→属性预测器（FastSpeech2 / SteerTTS / WordVoice / ToucanTTS 的 variance adaptor）学的是**某个语料的平均朗读习惯**（LJSpeech/LibriTTS 朗读，~150–170wpm、单一说话人）。我们是 0.7–1.0 变速 + 指定音色 + 表演性朗读，**绝对值必然系统性偏离**。这类模型只能回答「这个词相对邻词该不该更长/更高」，不能回答「这个 take 好不好」。

---

## 2. 候选表

| # | 引擎 | 给什么 | 粒度 | 许可/依赖 | 状态 |
|---|---|---|---|---|---|
| 1 | **TTScore-pro**（arXiv 2509.20485，github.com/rsmlgen/TTScore） | 给定文本，韵律 token（FACodec prosody + MFA 音素池化）的**条件似然**；音素级 → 可定位到词 | 音素/词 | 开源，需 FACodec + MFA + G2P | **未实测**（论文正文自述开源于该 repo，我没克隆） |
| 2 | **ProsodyEval / CWT prominence**（Talman 2019） | 每词一个连续 prominence 值（F0+energy+duration 平滑 z-norm 后合成 CWT 多尺度曲线）+ 2/3 分类 | **词** | 方法可复现，纯 numpy/scipy | 词级准确率 **85.3%**（对 Boston 专家标注）；**代码未确认开源** |
| 3 | **PyToBI**（github.com/monikaUPF/PyToBI） | 每词 break index 0–4 + pitch accent 有/无 | 词 | Python + Praat + TextGrid | **未实测**；break 位置 P **0.97** / 标签 **0.90**；tone 位置 0.77 / 标签仅 **0.47** ⇒ 只取 break，不取 tone |
| 4 | **OpenPronounce**（github.com/Halleck45/OpenPronounce） | 词级 expected/actual IPA + confidence + phoneme_error_rate + word_error_rate + prosody f0/energy 曲线 | 词/音素 | **MIT**，pip，CPU | **未实测**；README 完整；两个模型各 1.2GB |
| 5 | **faster-whisper 1.2.1** | 每词 start/end + probability（吞字/错读的代理） | 词 | MIT | **已装已验**（本机） |
| 6 | **parselmouth 0.4.7 + pyworld 0.3.5** | 每词 F0 均值/斜率/谐噪比、能量、时长 | 词（需对齐） | — | **已装已验**（本机） |
| 7 | **IntonaSphere AI**（github.com/ugozone/IntonasphereAI） | token 级 F0、半音归一化音高、末降斜率、强度、时长、plateau、末轮廓分类；28 列导出 | 词/token | 开源，faster-whisper + Parselmouth + WebMAUS | **未实测**；技术栈与我们完全重叠 |

**已被排除的**：
- **SteerTTS**：三个独立预测头（duration/pitch/energy）确实是我们要的形态，但**权重 CC BY-NC 4.0 非商用**（code MIT）⇒ 商业配音交付不能用。架构可借鉴。
- **WordVoice**：控制器，非分析器（见 §0）。
- **Azure Pronunciation Assessment**：标签体系最完整（`Monotone` / `UnexpectedBreak` / `MissingBreak` / `Mispronunciation` / `Omission` / `Insertion`），但云 API、收费、音频出境。**可用作标签体系参照系**，不作引擎。

---

## 3. 推荐组合（三层，不是三选一）

**L1 — 词级属性表（零新依赖，今天就能跑）**
```
faster-whisper(word_timestamps=True, word_probability)
  → 每词 start/end/probability
parselmouth + pyworld 在该区间内
  → F0 均值 / F0 斜率 / 半音标准差 / 能量 dB / 时长
CWT prominence（Talman 2019 重实现，~80 行）
  → 每词 prominence 值 + 2way 标签
```
产出列：`word, t0, t1, dur, f0_mean, f0_slope_st, f0_std_st, energy_db, prom, asr_prob, gap_before`

**L2 — reference-free 判分（要装，可选）**
TTScore-pro：只回答「给定这段文本，这段音频的韵律有多合理」。韵律塌平 → 似然低。这是**唯一**能同时吃「局部缺陷」且不需要真人参考的开源方案。

**L3 — 读音错误（要装，可选）**
OpenPronounce：只用来抓 word_error_rate 高的词，与韵律分开两个闸。

**兜底判据（零模型，最稳）**
> pdf2audiobook issue #1 原话：*"Compare to the render's own median profile (the centroid trick), which beats comparing to the reference because a reference is one utterance and a book is thousands."*

⇒ **不要拿外部预测器当标准答案，拿这一批 take 自己的中位数当标准。** 具体：对每条 take 算 prosody vector（F0 半音 std、能量 5–95pct 跨度、语速、停顿率、末字拉长比），然后 flag：
- 时长 > 3s 且 `f0_std < 0.5 × 批次中位` → 塌平
- 能量跨度 < 0.5 × 批次中位 → 塌平
- 远高于中位 → 喊叫 / 幻觉 register

这条判据在我们 955 条上**今天就能验证**，不需要任何新模型。

---

## 4. 为什么「预测每个词」要小心用

1. **绝对值不可比**：我们的 0.7–1.0 变速已经把 duration 缩过；预测器没见过这个语速。
2. **只取相对形状**：把预测值和实测值各自做句内 z-score，再比形状。直接比数会错。
3. **预测器不抓错误**：它只告诉你「该多长/多高」，不告诉你「读错了」。读音错必须走 ASR/GOP。
4. **同句双 take 互为参考最便宜**：同一句两个 seed，若某几个词在**两个 take 里都异常** → 文本/上下文问题；只有一个异常 → 该 seed 问题。零模型。

---

## 5. 下一步（等确认）

**POC-A（~30 min，零新依赖）**：在 955 条上跑词级属性表，用 §3 的 0.5× 中位判据 flag，统计：
- 能 flag 出多少条（预期十几到几十条）
- flag 出的和你们人工判过的 FIX/WATCH 重合多少
- 词级 F0 斜率能不能定位到「哪几个词平」

若 POC-A 重合度高 → 说明词级分辨率就是缺的那块，不必上 TTScore。
若重合度低 → 再上 TTScore-pro 做对照。
