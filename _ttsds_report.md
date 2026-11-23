# TTSDS2 PROSODY 因子评测（2026-10-27）

> 用户裁决：「换 TTSDS2 来，把之前相关性只有 0.3 的指标去掉，完全用不上」。
> 本报告是 TTSDS2 的第一次落地，也是 `loc` 轴的退役记录。

## 一、为什么换掉 loc

| | loc（旧） | TTSDS2 PROSODY（新） |
|---|---|---|
| 类型 | 单条音频的幅度型标量 | 整批音频的分布距离 |
| 与人耳相关 | **r = 0.30**（ProsodyEval 2025，logF0 RMSE 类） | **平均 Spearman 0.67**（16 个指标里唯一全情境 >0.50） |
| 判什么 | 词内 F0 高了几个半音 | 分布像不像真人（100=一致 / 0=噪声 / 50=等距） |

`loc` 还有一个独立问题：Prosogram 证明 `<pitch, semitones=9>` 抬的是**寄存器**不是**轮廓**
（同 seed 配对 51 对，副词核内滑幅 Δ **+0.00**，McNemar 上滑 9:8 / 下滑 10:10 全 50/50）。
所以它测到的「重音」在听感上不成立。

## 二、环境

| 项 | 值 |
|---|---|
| 包 | `ttsds` 2.1.3（已在本机） |
| Python | 3.10.11（`G:/Python310`） |
| 设备 | CPU（vanilla TTSDS2 的 prosody 模型全部 CPU-only） |
| 缓存 | `E:/ttsds/cache`（`TTSDS_CACHE_DIR`） |
| 模型 | HuBERT / MaskedProsodyModel 走 `hf-mirror.com`；Allosaurus `uni2005` 41.5 MB |

**只保留 prosody 四个 benchmark**：`ttsds/ttsds.py` 顶层会 import 全部 category，
把 speaker（wespeaker）、generic、intelligibility、environment 的 import 摘掉，
`BENCHMARKS` 收敛到四项。这样不需要 `pyannote-audio` / `wespeaker` / `pesq` 等重依赖。
（原文件备份在 `ttsds.py.bak_full`。）

### Windows 上必踩的两个坑

1. **`NamedTemporaryFile` 文件锁**：`allosaurus.py` 用 `with NamedTemporaryFile()` 后
   `soundfile.write` 会报 `System error`（Windows 句柄独占）⇒ 全部文件失败、分数变 NaN、
   而且被 `skip_errors=True` 吞掉。改成 `mkstemp` + `close` + `finally: remove`。
2. **模型目录名**：`latest.tar.gz` 解压出来是 `uni2005/`，但代码写死找 `latest/`，
   找不到就回头去 GitHub 下载（被墙）⇒ 同样静默失败。`cp -r uni2005 latest` 解决。

## 三、数据

| 集 | 内容 | 文件数 |
|---|---|---|
| 参考 | 真人《Wonder》母带切片（159 句 / 931 词） | 159 |
| delivered | 交付版 | 55 |
| cand | 打了重音标签的候选 | 94 |
| ctl | 同单元同 seed、**没打标签**的对照 | 51 |

TTSDS2 是分布级指标：两侧内容不必对应，只比特征分布。

## 四、结果

| 因子 | delivered | cand | ctl | 谁最好 |
|---|---|---|---|---|
| MPM（轮廓模式） | 90.04 | 91.67 | 93.07 | **ctl** |
| Pitch（F0 分布） | 91.26 | 79.77 | 83.95 | **delivered** |
| HuBERT 转换率（亚音素节奏） | 75.92 | 76.86 | 83.01 | **ctl** |
| Allosaurus 音素率（语速） | 77.44 | 74.88 | 80.23 | **ctl** |
| **PROSODY 均值** | 83.66 | 80.79 | 85.06 | **ctl** |

## 五、结论

### 1. 对照组（没打标签）韵律最像真人

`ctl 85.06` > `delivered 83.66` > `cand 80.79`。差值 **+1.40 分**。

### 2. 三个因子方向一致，只有 Pitch 反过来

| 因子 | delivered − ctl | 含义 |
|---|---|---|
| MPM | -3.03 | 对照更好 |
| Pitch | +7.31 | 交付版更好 |
| Hubert Token SR | -7.09 | 对照更好 |
| Allosaurus SR | -2.79 | 对照更好 |

**唯一的正项是 Pitch**：交付版的 F0 分布确实更贴真人（+7.31）。
但轮廓（MPM −3.03）、亚音素节奏（HuBERT −7.09）、音素语速（Allosaurus −2.79）三项全部倒退。

### 3. 一句话

> **标签把音高「搬到对的高度」，但把「怎么上去」弄丢了。**
> 这与 Prosogram 的独立证据完全一致（抬升是真的，轮廓是空的）。

## 六、局限（必须一起看）

1. **Prosody 因子本身与人耳的相关不高**：TTSDS2 论文 Table 6 给的是
   Clean 0.38 / Noisy 0.46 / Wild 0.34 / Kids 0.60，明显低于 Speaker 因子（0.59–0.86）。
   总分 0.67 是四个因子合起来的，不能当成「韵律分 0.67」。
2. **分布级不测「该重读的词有没有重读」**：它只看整体分布形状，
   不看单个词的位置对不对。所以它替代不了词级检查，只能做批次验收。
3. **参考是马修一个人一本书**：这是「这个风格」的参考，不是英语旁白的普遍规律。
4. **样本量**：ctl 51 条、delivered 55 条，分布估计有抖动，差 1.4 分不算大。

## 七、落地

| 动作 | 文件 | 状态 |
|---|---|---|
| `loc` 从判定链移除 | `mt_adv_fix.py` `judge()` / `judge_cand()` / adopt | ✅ |
| 单条判据只留 `rel_z` | `judge()` PASS = `rel_z ≥ 1.6` | ✅ |
| 批次验收用 TTSDS PROSODY | 本报告 + `_ttsds_run.py` | ✅ |
| 常量 `LOC_OK` / `LOC_DELTA_MIN` | 保留仅为兼容旧 state 字段名 | ✅ |

## 八、复现

```bash
python _ttsds_run.py --sets syn_delivered,syn_cand,syn_ctl \
    --bench mpm,pitch,hubert_token_sr,allosaurus_sr --out E:/ttsds/results_all.csv
python _ttsds_report.py
```

产物：`E:/ttsds/results_all.csv`（逐因子）、`_ttsds_report.md`（本文件）。
