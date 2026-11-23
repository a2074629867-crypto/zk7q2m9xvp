# EmphaClass 权重清单（官方完整仓库 + 本地残片现状）

> 2026-11-13 16:40 核。用途：**以后下到百度/云盘再用**，不在本机落地。
> 一句话：**权重存在且完整，只有一个官方源（Meta S3），没找到 HuggingFace / ModelScope 镜像。**

---

## 1. 官方三个文件（HEAD 实测 2026-11-13 16:38）

| 文件 | URL | Content-Length | Last-Modified |
|---|---|---|---|
| 英文分类器 | `https://dl.fbaipublicfiles.com/speech_expressivity_evaluation/EmphAssess/EmphaClass/EmphaClass-en.tar.gz` | **3,571,288,236** (3.33 GiB) | 2023-12-06 11:20:14 |
| 西语分类器 | `.../EmphaClass/EmphaClass-es.tar.gz` | **3,571,294,910** (3.33 GiB) | 2023-12-06 11:22:18 |
| EmphAssess 数据集 | `.../EmphAssess/EmphAssess_Dataset.tar.gz` | **226,646,154** (216 MiB) | 2023-12-06 11:15:21 |

英文那个 ETag = `7122220840982488d4ca747a5bda7010-426`（multipart，426 片），可用来做分片同步校验。

**下载后必查两件事**（这次就是没查，才以为路死了）：
1. `stat -c%s` 必须**等于**上表 Content-Length，差一个字节都算截断。
2. `tar -tzf 文件 | head` 能列目录，且 `tar -xzf` 不报 `unexpected EOF`；超大文件再加 `gzip -t` 验 CRC。

## 2. 镜像核查记录（都试过，无结果）

| 入口 | 结果 |
|---|---|
| `huggingface.co/api/models?search=emphaclass` | 走代理 HTTP 000（连不上） |
| `hf-mirror.com` 同上 | HTTP 503 |
| `hugging-face.cn/api/quicksearch?q=emphaclass` | 返回空 |
| `modelscope.cn` 搜索 | 无同名仓库 |
| WebFetch huggingface.co/models?search | fetch failed |

⇒ 结论：**没有现成镜像**。要么下官方 S3，要么自己下完传网盘（这也是用户说的“下到百度那里”）。

## 3. 本地残片现状（可直接删，别当资产）

- `D:/stress_tools/EmphaClass/EmphaClass-en.tar.gz` = **0 字节**（中断时被 curl 清空）
- `D:/stress_tools/emphaclass_en/pytorch_model.bin` = **253,372,928 B**，是那次 253MB 截断 tar 里解出来的前 242MB，**只占官方的 6.7%**，load 必炸（这就是 “failed finding central directory” 的来源）
- 旁边 `config.json` / `preprocessor_config.json` / `LICENSE.md` 是完整的（小文件在 tar 头部），留着有用，已抄进本文第 4 节

## 4. 架构事实（从本地完整的小文件读出，不靠论文）

- backbone：`facebook/wav2vec2-xls-r-1b`，48 层 / hidden 1280 / 16 头 / 约 10 亿参数
- 任务头：`Wav2Vec2ForAudioFrameClassification`（**帧级二分类**：是不是重读）
- 输入：**16kHz 单声道 wav**，帧步长 **20ms**
- 词级规则（论文 §5.2）：词内 **>50% 帧判 emphasized** 即该词重读
- 论文 F1：EmphAssess 词级 **93.48** / Expresso EN 词级 **78.40**

## 5. 为什么值得等

我们的需求是「筛出韵律没读到 / 塌成单模式」，缺的正是**音频侧“哪个词被强调了”**的判别器。
WhiStress 给的是文本+音频条件下的 per-word 概率（已跑通，与时长 rel_z 中位 ρ=0.31，与 F0/能量近零）；
EmphaClass 是纯声学帧级判别、不需文本对齐假设，两者互补。

## 6. 什么时候能跑

- 10 亿参数 XLS-R，CPU 上 20s 音频推理不现实（用户 2026-11-13 判定）
- 启用条件：**有 GPU（云端 V100/4090）或本机换卡之后**；届时把本文件第 1 节三个包下到云主机即可
- 只需英文那个 + 216MB 数据集（数据集用于复核它的 F1 93.5 是不是在我们这种文本上也成立）
