# -*- coding: utf-8 -*-
"""从 ttsds 结果 CSV 生成 PROSODY 报告。"""
import os
import pandas as pd

CSV = "E:/ttsds/results_all.csv"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ttsds_report.md")

ORDER = ["mpm", "pitch", "hubert_token_sr", "allosaurus_sr"]
LABEL = {
    "MPM": "MPM（轮廓模式）",
    "Pitch": "Pitch（F0 分布）",
    "Hubert Token SR": "HuBERT 转换率（亚音素节奏）",
    "Allosaurus SR": "Allosaurus 音素率（语速）",
}
KEY = {
    "MPM": "mpm",
    "Pitch": "pitch",
    "Hubert Token SR": "hubert_token_sr",
    "Allosaurus SR": "allosaurus_sr",
}
GROUPS = ["delivered", "cand", "ctl"]


def main():
    df = pd.read_csv(CSV)
    piv = df.pivot_table(index="benchmark_name", columns="dataset", values="score")
    piv = piv.loc[[k for k in LABEL if k in piv.index], GROUPS]

    L = []

    def A(s=""):
        L.append(s)
    A("# TTSDS2 PROSODY 因子评测（2026-10-27）")
    A()
    A("> 用户裁决：「换 TTSDS2 来，把之前相关性只有 0.3 的指标去掉，完全用不上」。")
    A("> 本报告是 TTSDS2 的第一次落地，也是 `loc` 轴的退役记录。")
    A()
    A("## 一、为什么换掉 loc")
    A()
    A("| | loc（旧） | TTSDS2 PROSODY（新） |")
    A("|---|---|---|")
    A("| 类型 | 单条音频的幅度型标量 | 整批音频的分布距离 |")
    A("| 与人耳相关 | **r = 0.30**（ProsodyEval 2025，logF0 RMSE 类） | **平均 Spearman 0.67**（16 个指标里唯一全情境 >0.50） |")
    A("| 判什么 | 词内 F0 高了几个半音 | 分布像不像真人（100=一致 / 0=噪声 / 50=等距） |")
    A()
    A("`loc` 还有一个独立问题：Prosogram 证明 `<pitch, semitones=9>` 抬的是**寄存器**不是**轮廓**")
    A("（同 seed 配对 51 对，副词核内滑幅 Δ **+0.00**，McNemar 上滑 9:8 / 下滑 10:10 全 50/50）。")
    A("所以它测到的「重音」在听感上不成立。")
    A()
    A("## 二、环境")
    A()
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 包 | `ttsds` 2.1.3（已在本机） |")
    A("| Python | 3.10.11（`G:/Python310`） |")
    A("| 设备 | CPU（vanilla TTSDS2 的 prosody 模型全部 CPU-only） |")
    A("| 缓存 | `E:/ttsds/cache`（`TTSDS_CACHE_DIR`） |")
    A("| 模型 | HuBERT / MaskedProsodyModel 走 `hf-mirror.com`；Allosaurus `uni2005` 41.5 MB |")
    A()
    A("**只保留 prosody 四个 benchmark**：`ttsds/ttsds.py` 顶层会 import 全部 category，")
    A("把 speaker（wespeaker）、generic、intelligibility、environment 的 import 摘掉，")
    A("`BENCHMARKS` 收敛到四项。这样不需要 `pyannote-audio` / `wespeaker` / `pesq` 等重依赖。")
    A("（原文件备份在 `ttsds.py.bak_full`。）")
    A()
    A("### Windows 上必踩的两个坑")
    A()
    A("1. **`NamedTemporaryFile` 文件锁**：`allosaurus.py` 用 `with NamedTemporaryFile()` 后")
    A("   `soundfile.write` 会报 `System error`（Windows 句柄独占）⇒ 全部文件失败、分数变 NaN、")
    A("   而且被 `skip_errors=True` 吞掉。改成 `mkstemp` + `close` + `finally: remove`。")
    A("2. **模型目录名**：`latest.tar.gz` 解压出来是 `uni2005/`，但代码写死找 `latest/`，")
    A("   找不到就回头去 GitHub 下载（被墙）⇒ 同样静默失败。`cp -r uni2005 latest` 解决。")
    A()
    A("## 三、数据")
    A()
    A("| 集 | 内容 | 文件数 |")
    A("|---|---|---|")
    A("| 参考 | 真人《Wonder》母带切片（159 句 / 931 词） | 159 |")
    A("| delivered | 交付版 | 55 |")
    A("| cand | 打了重音标签的候选 | 94 |")
    A("| ctl | 同单元同 seed、**没打标签**的对照 | 51 |")
    A()
    A("TTSDS2 是分布级指标：两侧内容不必对应，只比特征分布。")
    A()
    A("## 四、结果")
    A()
    A("| 因子 | " + " | ".join(GROUPS) + " | 谁最好 |")
    A("|---|" + "---|" * len(GROUPS) + "---|")
    for name in LABEL:
        row = [piv.loc[name, g] for g in GROUPS]
        best = GROUPS[row.index(max(row))]
        A("| %s | %s | **%s** |" % (LABEL[name], " | ".join("%.2f" % v for v in row), best))
    means = [piv[g].mean() for g in GROUPS]
    A("| **PROSODY 均值** | %s | **%s** |"
      % (" | ".join("%.2f" % v for v in means), GROUPS[means.index(max(means))]))
    A()
    A("## 五、结论")
    A()
    A("### 1. 对照组（没打标签）韵律最像真人")
    A()
    A("`ctl %.2f` > `delivered %.2f` > `cand %.2f`。差值 **%+.2f 分**。"
      % (means[2], means[0], means[1], means[2] - means[0]))
    A()
    A("### 2. 三个因子方向一致，只有 Pitch 反过来")
    A()
    A("| 因子 | delivered − ctl | 含义 |")
    A("|---|---|---|")
    for name in LABEL:
        d = piv.loc[name, "delivered"] - piv.loc[name, "ctl"]
        A("| %s | %+.2f | %s |" % (name, d, "交付版更好" if d > 0 else "对照更好"))
    A()
    A("**唯一的正项是 Pitch**：交付版的 F0 分布确实更贴真人（+%.2f）。"
      % (piv.loc["Pitch", "delivered"] - piv.loc["Pitch", "ctl"]))
    A("但轮廓（MPM −%.2f）、亚音素节奏（HuBERT −%.2f）、音素语速（Allosaurus −%.2f）三项全部倒退。"
      % (piv.loc["MPM", "ctl"] - piv.loc["MPM", "delivered"],
         piv.loc["Hubert Token SR", "ctl"] - piv.loc["Hubert Token SR", "delivered"],
         piv.loc["Allosaurus SR", "ctl"] - piv.loc["Allosaurus SR", "delivered"]))
    A()
    A("### 3. 一句话")
    A()
    A("> **标签把音高「搬到对的高度」，但把「怎么上去」弄丢了。**")
    A("> 这与 Prosogram 的独立证据完全一致（抬升是真的，轮廓是空的）。")
    A()
    A("## 六、局限（必须一起看）")
    A()
    A("1. **Prosody 因子本身与人耳的相关不高**：TTSDS2 论文 Table 6 给的是")
    A("   Clean 0.38 / Noisy 0.46 / Wild 0.34 / Kids 0.60，明显低于 Speaker 因子（0.59–0.86）。")
    A("   总分 0.67 是四个因子合起来的，不能当成「韵律分 0.67」。")
    A("2. **分布级不测「该重读的词有没有重读」**：它只看整体分布形状，")
    A("   不看单个词的位置对不对。所以它替代不了词级检查，只能做批次验收。")
    A("3. **参考是马修一个人一本书**：这是「这个风格」的参考，不是英语旁白的普遍规律。")
    A("4. **样本量**：ctl 51 条、delivered 55 条，分布估计有抖动，差 1.4 分不算大。")
    A()
    A("## 七、落地")
    A()
    A("| 动作 | 文件 | 状态 |")
    A("|---|---|---|")
    A("| `loc` 从判定链移除 | `mt_adv_fix.py` `judge()` / `judge_cand()` / adopt | ✅ |")
    A("| 单条判据只留 `rel_z` | `judge()` PASS = `rel_z ≥ 1.6` | ✅ |")
    A("| 批次验收用 TTSDS PROSODY | 本报告 + `_ttsds_run.py` | ✅ |")
    A("| 常量 `LOC_OK` / `LOC_DELTA_MIN` | 保留仅为兼容旧 state 字段名 | ✅ |")
    A()
    A("## 八、复现")
    A()
    A("```bash")
    A("python _ttsds_run.py --sets syn_delivered,syn_cand,syn_ctl \\")
    A("    --bench mpm,pitch,hubert_token_sr,allosaurus_sr --out E:/ttsds/results_all.csv")
    A("python _ttsds_report.py")
    A("```")
    A()
    A("产物：`E:/ttsds/results_all.csv`（逐因子）、`_ttsds_report.md`（本文件）。")

    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("写出", OUT, len(L), "行")
    print()
    print(piv.round(2).to_string())
    print()
    print("均值:", {g: round(v, 2) for g, v in zip(GROUPS, means)})


if __name__ == "__main__":
    main()
