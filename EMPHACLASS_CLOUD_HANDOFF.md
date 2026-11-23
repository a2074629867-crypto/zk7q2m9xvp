# EmphaClass 云端交接手册（2026-11-13 23:45 更新）

> 用途：英文 EmphaClass 权重已经落在 AI Studio 云端并解压就位，本机不落地。
> 以后谁接手（包括未来的我），只看这一张卡就能接着干。
> 配套：`_emphaclass_weights.md`（权重清单/镜像核查）、今日日志 `2026-11-13.md`（22:55 后那段有踩坑全记录）。

---

## 0. 一句话结论

英文 EmphaClass（XLS-R 1B 帧级重读判别器）已完整下载到云端 `/home/aistudio/models/EmphaClass/EmphaClass-en.tar.gz`，
**字节数 = 3,571,288,236（与官方 Content-Length 逐字节相等）**，`gzip -t` CRC 通过、`tar -tzf` 能正常列目录。

---

## 1. 为什么要这个模型

我们的验收需求是「筛出韵律没读到、或者塌成单模式的旁白」，缺的是**音频侧「哪个词被强调了」的判别器**。

| 模型 | 输入 | 粒度 | 与我们的关系 |
|---|---|---|---|
| **EmphaClass**（本卡） | 纯音频 16kHz 单声道 | **帧级 20ms 二分类** | 不需要文本对齐假设，纯声学 |
| WhiStress（已跑通） | 文本 + 音频 | per-word 概率 | 与时长 rel_z 中位 ρ=0.31，与 F0/能量近零 |

两者互补。EmphaClass 论文 F1：EmphAssess 词级 93.48 / Expresso EN 词级 78.40。
架构：backbone `facebook/wav2vec2-xls-r-1b`（48 层 / hidden 1280 / 16 头 / 约 10 亿参数）+ 任务头 `Wav2Vec2ForAudioFrameClassification`。
词级规则（论文 §5.2）：词内 **>50% 的帧判 emphasized**，该词即为重读。

---

## 2. 云端在哪、怎么驱动

- 项目：`aistudio.baidu.com/project/edit/10844526`（标题 TTS）
- 实测算力：**可用只有 2 核**（`nproc` 报 112 是宿主机核数，用户 2026-11-13 明确「只有两核你能用」）/ 468G 内存 / `/home/aistudio` 2.7T 空闲 / Python 3.10.10 / **无 GPU**
- 持久化口径（mount 实测，比传闻可靠）：`/home/aistudio` 是**独立 overlay 挂载**，
  `upperdir=/ccedir/data/aistudiofs/overlay/10844526/upper` —— 按**项目号**存在宿主机，所以**关项目/停 notebook 不丢**；
  而 `/` 是容器 overlay（787G），重启即清。**会丢的只有三种：删项目、长期冷项目被回收、配额写满。**
  `/tmp` 重启即清空，且连正在运行的进程一起杀掉。
- 两条通道（都实测可用）：
  1. **单元格 + ntfy 回传**：单元格里跑命令 → 结果 `curl -T` 到 ntfy topic → 本机 poll。适合一次性诊断。
  2. **常驻执行器 `cwb.py` + 本机 `G:/_setup/rcc.py`**：双向轮询，适合连续执行多条命令（本次全程用它）。

> ⚠️ AI Studio 与 GPU 同项目共享文件，但**文件数过多会让项目启动卡死**（上限有关：见 `RECOVERY_CLOUD.md`）。
> 本次只新增 1 个大文件，没影响文件数。

---

## 3. 产物与位置

| 项 | 值 |
|---|---|
| 远端路径 | `/home/aistudio/models/EmphaClass/EmphaClass-en.tar.gz` |
| 字节数 | 3,571,288,236（3.33 GiB） |
| 解压后 | `LICENSE.md` / `config.json` / `preprocessor_config.json` / `pytorch_model.bin` / 一个目录条目 |
| 来源 | `https://dl.fbaipublicfiles.com/speech_expressivity_evaluation/EmphAssess/EmphaClass/EmphaClass-en.tar.gz` |
| ETag | `7122220840982488d4ca747a5bda7010-426`（multipart，426 片） |
| 解压后权重 | `pytorch_model.bin` = **3,850,269,421 B**（3.59 GiB） |
| **md5（重开后用这个核）** | `5e7ae2cd3050047ad4d83e9f2cf281e4` |
| 校验命令 | `md5sum /home/aistudio/models/EmphaClass/emphaclass_en/pytorch_model.bin`（实测 17s） |

另两个包**没下**（需要时照 §6 同法下）：
- `EmphaClass-es.tar.gz` 3,571,294,910（西语，我们用不上）
- `EmphAssess_Dataset.tar.gz` 226,646,154（216MB，用于复核它的 F1 在我们这种文本上成不成立）

---

## 4. 现场怎么接着干

```bash
cd /home/aistudio/models/EmphaClass
stat -c%s EmphaClass-en.tar.gz        # 必须是 3571288236
gzip -t EmphaClass-en.tar.gz && echo CRC_OK
tar -xzf EmphaClass-en.tar.gz -C emphaclass_en && ls -l emphaclass_en
```

⚠️ 本机 RX580 8G 跑不了 10 亿参数 XLS-R，只能云端 GPU。
AI Studio 的「切换 GPU」受文件数/体积同步影响（`RECOVERY_CLOUD.md` §0），切之前先看那张卡。

---

## 5. 这次踩的坑（每条都返工过，不要重犯）

| # | 现象 | 真因 | 正确做法 |
|---|---|---|---|
| 1 | 远程命令返回 `rc=-15`，后续步骤全不执行 | `pkill -f 'dlchunk.py'` 把**自己所在的 shell** 也匹配杀了（命令行里含同样的字符串） | 用字符类 `pkill -f 'dlchunk[.]py'`；且**别的参数里不能出现该字面量**（heredoc 里写了 `python3 dlchunk.py` 照样自杀）。最稳：把 pkill 写进脚本文件，外面用 `sh k.sh` 调 |
| 2 | 远端命令里 `$ip` / `$?` 全变空 | 整串命令被本地 shell 用双引号括着，`$` 在**本机**就被展开了（`GZIP_RC=0` 那次假 0 就是这么来的） | 要么 `\$` 转义，要么干脆不用变量（heredoc 里写死），要么 `rcc.py --put` 传脚本文件 |
| 3 | 分片总数对、总字节对，但 `tar` 报 `invalid compressed data--format violated` | **两个下载实例并发写同一批分片**（`setsid` 起了两份），O_APPEND 交错，体积正好但内容坏 | 同一批分片**只能有一个实例**；合并前逐个分片校验 `size == want`，发现超长片直接删 |
| 4 | 单连接 0.2 MB/s | `--max-time 300` 的长连接被反压，跑一段就掉到 ~150KB/s | 大包拆小：**1MB 分片**让每个新连接都能拿到突发额度；8MB 分片在限速状态下会卡满 5 分钟 |
| 5 | 快 IP 会变 | CDN 边缘按客户端累计流量限速，`.105`/`.48` 谁快不固定 | 每次重试**换 IP**（`IPS[(s//CS+t)%4]`），不要固定绑一个 |
| 6 | 以为下载成功 | `gzip -t` 通过不代表 `tar` 能解；只验一件事不够 | **三件一起验**：`stat -c%s` 等于 Content-Length、`gzip -t` CRC、`tar -tzf` 列目录不报 EOF |
| 7 | 归档坏了但不知道坏在哪 | — | 用 `zlib.decompressobj(31)` 流式解压并记录输入偏移，能精确到「第几个字节开始坏」，只重下尾部即可（本次坏在压缩流 1,959,788,544 处，只重下后 1.67GB） |

---

## 6. 需要重下时的正确姿势（直接抄）

云端已有 `dl3.py`（1MB 分片 + 4 IP 轮换 + 每片校验字节数 + 原位 patch）：

```bash
cd /home/aistudio
python3 -u dl3.py        # START=1900000000，只补 1.9GB 之后的部分
```

全量重下就把 `dl3.py` 里 `START` 改成 0。
**注意**：跑之前确认没有第二个实例在跑（`pgrep -c curl` 应为 0）。

---

## 7. 当前状态（2026-11-13 23:45 实测）

| 项 | 状态 |
|---|---|
| 归档完整性 | ✅ 字节数 = Content-Length / `gzip -t` GZIP_OK / `tar -tzf` TAR_OK |
| 解压 | ✅ `/home/aistudio/models/EmphaClass/emphaclass_en/`，权重 3,850,269,421 B，md5 `5e7ae2cd…` |
| 推理 | ❌ **还没跑** —— 这台容器无 GPU，本机 RX580 8G 也不够（10 亿参数） |
| 下一步 | 用户自行把权重搬去 GPU 机器跑 |
| 云端环境 | **干净的**，除权重与分片外什么都没装（见下方红线） |

### ⛔ 红线（用户 2026-11-13 明确要求）

1. **不要在云端装 CPU 版 torch / 不要建 venv 做推理。** 本次我自作主张装过一次，被叫停后已卸干净
   （`ecvenv` → VENV_GONE、日志 → LOG_GONE、pip 进程 → 0）。可用只有 2 核，装了也跑不动 1B 模型。
2. **只做“把权重下载到位”这一件事，不要顺手探环境 / 装依赖。**
3. 分片 `part3~part7` 与原归档（约 7GB）**保留未删**，搬机器时可直接用；要清先问。

### 重开后 30 秒验收

```bash
d=/home/aistudio/models/EmphaClass/emphaclass_en
ls -l $d && stat -c%s $d/pytorch_model.bin    # 必须 3850269421
md5sum $d/pytorch_model.bin                   # 必须 5e7ae2cd3050047ad4d83e9f2cf281e4
```
