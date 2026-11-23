# 真人语料采集方案

> **日期**：2026-11-01
> **目标**：给 Joseph / Helena / Fielding 找参考音（5 条 ref）
> **前提**：自用，授权不做约束，只按「能不能拿到数据」排

---

## 一句话结论

**TTS 厂商不买语料，他们抓语料。**

Emilia（当前最大的开源语音库，21.6 万小时）就是这么做的：从播客、脱口秀、有声书里抓，然后跑一条六步流水线。**600 小时原始音频最后只留 29%**，剩下的就是训练数据。

这条路你能直接复现——你的本职就是干这个。

---

## 一、三条路，先选方向

| 路 | 做法 | 成本 | 周期 | 质量特点 | 适合找什么 |
|---|---|---|---|---|---|
| **A** | 下现成库 | 带宽 | 小时级 | 干净，但「念得对」 | 基础音色、说话人基数 |
| **B** | 抓 + 跑 Emilia-Pipe | 算力 | 天级 | 可控，能筛 | 大量候选，规模化 |
| **C** | 直接抓表演 | 爬虫 | 天级 | **最接近真实对白** | 「虚、犹豫、爱绕圈子」这类质感 |

### ★ 关键判断：你要的质感只在 C 路里

**「虚、犹豫、爱绕圈子」在朗读语料里几乎不存在。** 朗读者都在「正确地念」——字正腔圆、语速均匀、不犹豫。

这类质感只在**表演**里出现：演员在演一个没底气的人，会真的卡壳、真的重复、真的把尾音掉下去。

所以：
- **A 路用来找「音色基数」**（谁的声音频率对）
- **C 路用来找「质感」**（谁真的在演一个虚的人）
- **B 路是中间件**（把 C 路抓来的东西处理成可用片段）

---

## 二、A 路：现成库清单

### 2.1 多人朗读 —— 找 Joseph 的中年男声、Helena 的成年女声

| 库 | 规模 | 说话人 | 采样率 | 地址 | 备注 |
|---|---|---|---|---|---|
| **LibriTTS-R** | 585 h | 2,456 | 24k | `openslr.org/60` | **优先用这个**，音频修复版，句级切分 |
| LibriTTS | 585 h | 2,456 | 24k | 同上 | 原始版，音质略差 |
| **VCTK** | ~44 h | 110 | **48k** | `datashare.ed.ac.uk/handle/10283/2651` | **采样率最高**，多口音，适合做 ref |
| **VoxCeleb 1/2** | 2,000+ h | 7,000+ | 16k | `robots.ox.ac.uk/~vgg/data/voxceleb` | YouTube 访谈，**中年男女极多** |
| Emilia | 英 46.8k h | — | 24k | `huggingface.co/datasets/amphion/Emilia-Dataset` | in-the-wild，自发语音 |
| MLS | 50k h / 8 语 | — | 16k | `openslr.org/94` | LibriVox 派生 |
| Libri-Light | 60k h | — | 16k | `github.com/facebookresearch/libri-light` | 无标注 |

**LibriTTS 是源头**：LibriSpeech / LibriTTS / MLS / Libriheavy 全从 **LibriVox**（公共领域有声书）来。LibriVox 有 2,456+ 朗读者，是最大的免费「多人朗读」池。

### 2.2 情绪语料 —— 找「虚 / 犹豫 / 气声」的标注

| 库 | 说话人 | 情绪 | 地址 | 为什么适合 |
|---|---|---|---|---|
| **CREMA-D** | 91（**年龄 20–74**） | 6 | `github.com/CheyneyComputerScience/CREMA-D` | **有年龄跨度，找 50+ 男声首选** |
| **ESD** | 10 英 + 10 中 | 5 | `hltsingapore.github.io/ESD` | **同一人同一文本多情绪**，结构最契合 |
| **MSP-Podcast** | 大量 | 情绪标注 | `ecs.utdallas.edu/research/researchlabs/msp-lab/MSP-Podcast.html` | in-the-wild 播客，**最接近真实对话** |
| RAVDESS | 24（12 男 12 女） | 8 | `zenodo.org/records/1188976` | 北美口音，演员表演 |
| EmoV-DB | 5 | 4 | `github.com/numediart/EmoV-DB` | 含 **whisper 档** |
| SAVEE | 4 男 | 7 | `kahlan.eps.surrey.ac.uk/savee` | 小但干净 |
| JL-Corpus | 4 | 5 | `github.com/tli725/JL-Corpus` | 英式英语 |
| EMO-DB | 10 | 7 | `emodb.bilderbar.info` | 德语，但情绪表演质量高 |

### 2.3 童声 —— Fielding 唯一来源

| 库 | 规模 | 年龄 | 地址 | 备注 |
|---|---|---|---|---|
| **MyST** | 400 h / 230K 条 | **3–5 年级（8–11 岁）** | `myst.cemantix.org` | 1,300 学生，**年龄最契合** |
| **CSLU Kids** | 1,100 儿童 | K–10 年级 | LDC2007S18 | 每人 8–10 分钟，含自发语音 |
| **CHILDES-Aligned** | 501,880 条 / 413 h | 0;6–14;3 | `talkbank.org/childes/access/Derived/CHILDES-Aligned.html` | 量最大，但 16k |
| CMU Kids | — | 小学 | LDC97S63 | 朗读 |
| OGI Kids | — | 儿童 | — | 电话语音 |

---

## 三、B 路：Emilia-Pipe（工业级流水线，开源）

**这是 TTS 厂商的标准做法。** 代码在 `github.com/open-mmlab/Amphion/tree/main/preprocessors/Emilia`。

### 六步

| 步 | 工具 | 参数 | 作用 |
|---|---|---|---|
| 1 标准化 | ffmpeg | 24kHz / mono / −20dBFS | 统一格式 |
| 2 人声分离 | **UVR-MDX-Net** | SDR ≈ 11.15dB | 去音乐、去背景 |
| 3 说话人分离 | **pyannote 3.1** | — | 切单人区间 |
| 4 VAD 切分 | **Silero-VAD** | 3–30s | 切段（ROC-AUC 0.99） |
| 5 ASR | **WhisperX** (medium) | 时间对齐 | 转写 |
| 6 过滤 | — | 语种置信 ≥80% + **DNSMOS P.835 OVRL ≥3.0** + 语速 IQR 去异常 | 筛质量 |

### 关键数字

- **600 小时测试片只保留 ~29%**
- DNSMOS 从 2.50 提到 **3.26**（接近录音棚水平）
- 平均段长 **~9 秒**（正好落在我们 3–8s 的要求附近）
- **RTF 0.006** —— 1000 小时音频 6 小时处理完

### 你能怎么用

| 原流程 | 你的替代 |
|---|---|
| WhisperX | **Parakeet TDT v3**（你已有，`asr_venv`） |
| pyannote | CAM++ / ECAPA（你已有 `spk_embed.py`） |
| DNSMOS | `pip install speechmos`（已装过） |
| UVR | 需要装，但 RX580 上可能慢，可以先用 ffmpeg 高通 + 简单降噪替代 |

★ 注意：**这套流程是为「量大」设计的**。你只有 5 条 ref，跑完整流水线是杀鸡用牛刀。**先用它处理 C 路抓来的长音频**（一部剧、一期播客），再人工挑。

---

## 四、C 路：自己抓（优先级最高）

### 4.1 抓什么

| 源 | 为什么 | 怎么抓 | 备注 |
|---|---|---|---|
| **YouTube 英剧 / 电视剧** | 有真实的父子对话、训斥、讨好 | `yt-dlp` | 优先找英国剧（本书是英国背景） |
| **播客** | 中年男声密度最高，天然长对话 | RSS 抓取 | 访谈类最好，有犹豫、有停顿 |
| **LibriVox** | 公共领域，2,456+ 朗读者，音质干净 | 直接下 mp3 | 找「读得慢、声音虚」的朗读者 |
| **Audible 试听片段** | 专业配音，正是「角色表演」 | 短片段 | 一段 5 分钟，含多个角色 |
| **TED / 访谈节目** | 说话人标签清晰 | — | 适合找 Helena 那种「明亮带喘」 |
| **有声书 YouTube 频道** | 免费、长、单人 | `yt-dlp` | 童书朗读 → Fielding |

### 4.2 抓取要点

- **不要抓音乐/带 BGM 的**：UVR 分离会引入伪影
- **优先抓「对话密集」的**：独白里没有互动，就没有「对谁说话」的质感
- **一次抓 30~60 分钟**：够长，能出多个候选；又不至于处理太久
- **记下时间码**：后面要回切

---

## 五、四层检索漏斗（怎么在大堆里找到目标音色）

前三层你已有工具（`voice_lib/_scan.py` / `_cluster.py`），只是没跑完。

| 层 | 方法 | 工具 | 过滤掉 |
|---|---|---|---|
| **1 粗筛** | F0 + 谱质心 + HNR + wpm | parselmouth + numpy（`_scan.py` 已实现） | ~90% |
| **2 说话人聚类** | embedding 余弦聚类，找「同一人有多段」 | CAM++ / ECAPA（`_cluster.py` 已实现） | 只留候选人物 |
| **3 语义检索** | 文字找音频 | **CLAP**（`laion/clap-htsat-fused`） | 按音色描述筛 |
| **4 情绪标注** | 自动打情绪标签 | **emotion2vec+ large** | 按情绪筛 |

### 5.1 第一层：粗筛（最便宜，先做）

`_scan.py` 已经实现了这套：按能量切语音岛 → 逐段测 F0 / HNR / 谱平坦度 / 谱质心 → 按 F0 分档（adult_male / adult_female / child）。

**改一下就能扫任意目录**（现在是硬编码 `film16k.wav`）。

### 5.2 第二层：说话人聚类

`_cluster.py` 已经实现了：CAM++ 嵌入 → 余弦聚类 → 找出「同一个人出现多次」的簇。

★ **注意**：CAM++ 不能用来判「是不是同一个人」（AUC 0.491 = 随机），但**可以用来聚类**——把「听起来像同一个人」的段归到一起。这两个任务不一样。

### 5.3 第三层：CLAP 语义检索

这是「用文字找声音」，可以真的写一句话去搜：

```python
from transformers import ClapModel, ClapProcessor
import torch

model = ClapModel.from_pretrained("laion/clap-htsat-fused")
proc = ClapProcessor.from_pretrained("laion/clap-htsat-fused")

# 音频 → 512 维向量
inputs = proc(audios=audio, return_tensors="pt", sampling_rate=48000)
avec = model.get_audio_features(**inputs)

# 文本 → 同一个空间
tinputs = proc(text=["a hesitant middle-aged man, soft breathy voice"], return_tensors="pt", padding=True)
tvec = model.get_text_features(**tinputs)

# 余弦相似度
sim = torch.cosine_similarity(avec, tvec).item()
```

★ 注意：CLAP 的跨模态分数**不是** 0~1 的绝对相似度。0.3 已经可能是强匹配。所以只能用来**排序**，不能设绝对阈值。

### 5.4 第四层：情绪标注

`emotion2vec+ large`（emocean 数据集用的就是它，9 类）。可以用来筛「犹豫/低唤醒」的段。

---

## 六、三个角色的具体打法

| 角色 | 目标参数 | 首选源 | CLAP 检索词 | 难点 |
|---|---|---|---|---|
| **Joseph** | F0 **110–130Hz** / HNR 低 / **235–245 wpm** / 句内长停顿多 | **MSP-Podcast** + **CREMA-D（50+ 组）** | `a hesitant middle-aged man, soft breathy voice, unsure` | 「犹豫」在朗读里没有，只能去播客/表演里找 |
| **Helena** | 谱质心 **≥1450Hz**（≥1.30× E_calm 1116）/ 240 wpm / 句尾上扬 | **VCTK（48k）** + **ESD** | `a bright warm woman speaking eagerly, slightly breathless` | 两个档要来自**不同录音**，不能一段调音量 |
| **Fielding** | 与 Charles 同 F0 区但谱质心 **>1830**（>1.28×）/ **280+ wpm** | **MyST（8–11 岁）** + **CSLU Kids** | `a confident boy speaking quickly, clear voice` | 儿童语料多是「回答问题」，语速普遍慢，可能只能接受降一档 |

### 6.1 Joseph 的两档怎么找

- **`J_base`**（虚、绕）：找「说话没底气、爱铺垫、句子长」的中年男。播客里那种「嗯…这个嘛…其实我是这么想的」最像。
- **`J_bluster`**（虚张声势）：找「突然拔高、但底气不足」的段。**关键是要「装」的感觉**——音量上去了，气息还是虚的。这在吵架戏里很常见。

★ 两档必须来自**不同录音**。同一段调音量做不出「装」的质感。

### 6.2 Helena 的两档

- **`H_base`**（明亮带喘）：找「用力推销自己」的女声。TED 演讲、房产中介、导购都是这个调。
- **`H_sweet`**（对 Edmund 的软亮）：找「对小孩说话」或「哄人」的段。

★ 只服务 2 条台词，但那是全书情绪峰值。

### 6.3 Fielding 只有一档，但最难

**wpm 280+ 是硬指标**，因为不能加速（tempo 上限 1.00）。

儿童语料普遍慢（孩子在「回答老师问题」）。所以：
- 优先找**孩子之间吵架/炫耀**的素材（快、急、打断）
- MyST 是「科学辅导对话」，可能偏慢，但量大可以筛
- 实在找不到 → **接受降一档**，用停顿（0.20s）和包络（平收）补

---

## 七、筛选脚本骨架

现有 `voice_lib/_scan.py` 是硬编码单文件，改成扫目录：

```python
# _scan_dir.py —— 扫任意目录，输出候选清单
import glob, os, json, numpy as np, soundfile as sf
from _scan import islands, measure, HOP_SEC   # 复用已有函数

def scan_dir(root, out="candidates.json"):
    rows = []
    for f in sorted(glob.glob(os.path.join(root, "**/*.wav"), recursive=True)):
        x, sr = sf.read(f, dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        # 统一到 16k（_scan 的口径）
        if sr != 16000:
            import librosa
            x = librosa.resample(x, orig_sr=sr, target_sr=16000)
            sr = 16000
        for a, b in islands(x, sr):
            m = measure(x, sr, a, b, int(HOP_SEC * sr))
            if m:
                rows.append(dict(file=f, start=round(a * HOP_SEC, 2),
                                 end=round(b * HOP_SEC, 2), **m))
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    return rows
```

然后按角色目标过滤：

```python
# Joseph 候选
jos = [r for r in rows
       if r["band"] == "adult_male"
       and 110 <= r["f0"] <= 130
       and r["hnr"] < 12          # 气声多
       and r["dur"] >= 3.0]

# Helena 候选
hel = [r for r in rows
       if r["band"] == "adult_female"
       and r["cent"] >= 1450
       and r["dur"] >= 3.0]

# Fielding 候选
fld = [r for r in rows
       if r["band"] == "child"
       and r["cent"] >= 1830
       and r["dur"] >= 3.0]
```

---

## 八、验收标准

一条候选要进 ref，必须同时满足：

| 项 | 标准 | 怎么测 |
|---|---|---|
| 时长 | 3–8 秒 | `sf.info` |
| 采样率 | ≥24k（最好 48k） | `sf.info` |
| SNR | ≥15 dB | 语音帧 vs 静音帧电平差 |
| 语音占比 | ≥60% | VAD |
| 转写 | 与音频严格对应 | ASR + 人工核 |
| 中性度 | **同档 6–10 条互比 ≥0.65** | 声纹 |
| 与旁白距离 | F0 ≥4 半音（Joseph） | parselmouth |
| 与主角距离 | 谱质心比 ≥1.28~1.30 | numpy FFT |

★ **最后一条最容易漏**：候选单独听很好，但和 Charles / Edmund 放一起就分不出来。**必须和已有 4 档做碰撞检查。**

---

## 九、建议的执行顺序

```
1. 先跑 A 路的下现成库（LibriTTS-R + VCTK + CREMA-D + MyST），半天内能拿到第一批候选
   ↓
2. 用 _scan.py 扫一遍，按三个角色的目标参数粗筛
   ↓
3. 人工听 20~30 条 top 候选，挑出 3~5 个「方向对」的
   ↓
4. 只对这 3~5 个走 C 路（找他们的其他录音、或抓更多素材），凑够 6~10 条/档
   ↓
5. 碰撞检查（和 Charles / Edmund 对比），不合格换人
```

★ **不要一开始就抓一堆素材跑 Emilia-Pipe**。你只有 5 条 ref，先用手工筛更快。

---

## 附：相关文件

| 文件 | 用途 |
|---|---|
| `voice_lib/_scan.py` | 已有：F0/HNR/flat/cent 分档扫描（需改成扫目录） |
| `voice_lib/_cluster.py` | 已有：CAM++ 嵌入 + 余弦聚类 |
| `voice_lib/_scan.json` | 原片 601 段语音岛分档（男 303 / 女 117 / 童 166） |
| `_dialog_tuning.md` | 档位映射与停顿表（找完之后怎么用） |
| `cloud/ref/cast.json` | 角色 → ref 映射，找到后填这里 |
