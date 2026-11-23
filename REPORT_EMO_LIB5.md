# 新角色切片 × 情绪判定 → 五角色音色库（2026-11-09）

把三个新角色（Fielding / Helena / Joseph）的全部切片过一遍情绪判定引擎，每类情绪取
3 条不同语气的成品，做成「角色 × 情绪档」的多音色库。顺带修掉了一个多片合库才会
暴露的归一化 bug。

---

## 一、交付物

| 文件 | 内容 |
|---|---|
| `_emo_refs_all.json` | **五角色生产库**：Charles 10 + Thomas 15 + Fielding 15 + Helena 15 + Joseph 15 = **70 条模板** |
| `refs_cast/<角色>_<档>_<id>.wav` | 45 个新 wav（三新角色 × 5 档 × 3 条） |
| `_bg_map.json` | 多片合库必须的**分域 Z-norm 背景配置**（角色 → 该角色所在片的背景集） |
| `verify_lib.py` | 库自检：留一法 + 跨角色混淆（多角色库通用） |
| `fair_score.py` | 打分规则对比实验（1-NN / top2 / top3 / 角色内 z） |

单角色库仍分别保留：`_fielding_refs.json`、`_helena_mary_refs.json`、`_joseph_refs_emo.json`。

## 二、三新角色的档位内容

档名固定为 `excited / defiant / wronged / wary / nervous`，对应引擎的五类判据
（兴奋 A×V、激动反抗 D、委屈 1−A、警惕 e2v disgusted、紧张 A×(1−D)）。每档 3 条是
不同场次的语气，不是同一句的三个变体 —— 这就是「多音色」的用法：同一情绪可以换
一条参考音重生成，避免整本书都是同一条模板的腔。

### Fielding（Son of Rambow 2007 / Lee Carter / Will Poulter，F0 中位 197）

| 档 | 三条（emo 值 / 时长 / 台词） |
|---|---|
| excited | 0.43 3.7s "He's even worse than that bloody French…" · 0.40 4.0s "He could if he wanted to, though." · 0.38 2.8s "We've got ten minutes before lessons." |
| defiant | 0.70 3.9s "Had to be the one with the bloody trailer on." · 0.69 4.9s "I don't mean another watch. I get to choose." · 0.69 7.3s "I swear to God, if you tell anyone I'm making…" |
| wronged | 0.79 4.7s "But, er, if I do, you, er, might have to give…" · 0.74 4.1s "You, er, left your alarm clock in my locker." · 0.73 7.5s "The last time she tortured me…" |
| wary | 0.98 3.2s "their bone goes up through their brain and kills 'em" · 0.70 3.0s "Didn't you know? About the torture?" · 0.11 3.3s "Doctor said they might have to amputate it" |
| nervous | 0.28 3.1s "Well, can't keep the lady waiting, can we?" · 0.27 3.2s "My brother is the worst actor ever." · 0.27 5.8s "You know, I've been thinking. The watch is…" |

### Helena（Another Year 2010 / Mary / Lesley Manville，F0 中位 233）

| 档 | 三条 |
|---|---|
| excited | 0.62 7.8s "And you can't cook. No. Well, I can a bit…" · 0.58 5.8s "You should come out and have a drink with us." · 0.52 8.5s "Did Jerry tell you about me getting a car?" |
| defiant | 0.69 7.6s "it's taken me three hours to get I left home" · 0.68 8.0s "Yeah, it was a bit unsettling, to be honest." · 0.67 4.8s "was gonna go around with the money" |
| wronged | 0.81 4.5s "I do feel a bit guilty, though…" · 0.59 2.1s "a man in? Cost too much." · 0.58 2.6s "plastic bags, and shove them under the bed." |
| wary | 0.03 4.2s "I've just had to have a cigarette" · 0.02 4.0s "I've got my independence" · 0.02 2.3s "It's not all rosy." ⚠ 判据退化，见 §五 |
| nervous | 0.27 4.2s "I still think about that. We had a barbecue" · 0.27 3.6s "you're allowed a couple glasses" · 0.27 2.3s "I don't really smoke normally" |

### Joseph（Hope Gap 2019 / Edward / Bill Nighy，F0 中位 116）

**已补字幕重切（2026-11-09 晚）**：yifysubtitles 上这部片只有西语，改走 subf2m
（3 份英文）。字幕与我们的 YTS 蓝光版差 **−21 秒**（两条独立证据：ASR 词落在字幕窗内的
比例 79.7%→98.3%，能量 cue 窗比随机窗 +0.2dB→+3.6dB）。修正后切出 1474 条带原文的 cue。

| 档 | 三条（原文 / emo） |
|---|---|
| excited | "I suppose I was half dazzled by her in the beginning." 0.46 · "You can love somebody and want to leave them at the same time." 0.43 · "but I feel guilty because I'm happy and she isn't." 0.41 |
| defiant | "The truth is I made a mistake about Grace right at the beginning" 0.60 · "I knew that all my life I'd wanted his embrace" 0.60 · "Angela felt why drag it out." 0.58 |
| wronged | "She was looking at me as if she was sorry for me." 0.78 · "Yes, it's not easy to explain." 0.71 · "It's not really working is it?" 0.71 |
| wary | "All it took was Angela's hand on my arm, her touch." 0.78 · "She wants to make a scene, but I won't be drawn in, Jamie." 0.27 · "That makes me feel, well, not much good really." 0.18 |
| nervous | "And she never really forgave me for not being him." 0.28 · "I'm no good for you, Grace." 0.27 · "I think you want something I haven't got." 0.27 |

- 种子 4 条（2793.2 / 3595.8 / 3762.0 / 4849.0），种子留一法 0.579–0.793
- 扩出 63 条候选，组内 0.73–0.82、跨角色 ≤0.20（上一版无文本时是 0.53–0.82 / ≤0.23）
- ⚠ 种子 253.6s（"Less than 20,000 came back."，F0 191Hz）是课堂上学生的回答，已剔除

## 三、库自检（`verify_lib.py`）

```
五角色 / 70 条模板
留一法（组内 >= 跨角色） 69/70 = 98.6%
唯一失败：Charles/soft 组内 0.388 < Fielding 0.480
```

旧四角色库（45 条）也是 44/45，失败的是同一条 —— 这条 Charles 低声句
（"Tu peux plus rien me faire, maintenant"）本来就被轻声音色吸，与本次新增无关。
F0 分档：Joseph 116 / Fielding 197 / Helena 233（Charles 294 一档，Thomas 200 左右）。

## 四、⚠ 多片合库会掉分 —— 是归一化的锅，不是库的锅

59 条法语片真值回放：

| 方案 | 模板 | PASS | PASS 纯度 | 总准确率 |
|---|---|---|---|---|
| 基线（两角色库） | 25 | 38 | 100% | 86.4% |
| 五角色库 + 单一背景集 | 70 | **17** | 100% | **47.5%** |
| 五角色库 + 分域背景集 | 70 | 36 | 100% | 84.7% |

排查过程：

1. **先怀疑 1-NN 偏向模板多的一方** → 写 `fair_score.py` 对比 1-NN / top2 均值 /
   top3 均值 / 角色内 z。结果：原始余弦 1-NN 在 25 和 70 条模板上**都是 96.6%**，
   规则本身没问题。
2. **再看 Z-norm 的 μ/σ** → 同一套背景集（城堡 393 条儿童对白）归一化所有模板：

   | 角色 | μ | σ |
   |---|---|---|
   | Charles | 0.13–0.25 | 0.13–0.18 |
   | Joseph | 0.01–0.10 | 0.06–0.11 |

   Joseph 模板跟法语片台词本来就远，μ 低、σ 更小 ⇒ 一点点相似度就放大成 z≈+3，
   直接把法语片台词全吸走。
3. **修法**：`EmoVoice(bg_map={角色: 该角色所在片的背景集})`，每个模板只用**自己那部片**
   的普通句子做归一化。`_bg_map.json` 已存好，命令行 `--bg-map "@G:/_setup/_bg_map.json"`。

剩下的 2 条差距（36 vs 38）来自 45 个跨片模板的正常竞争成本，纯度仍是 100%。

## 五、已知短板（写进交付说明，别当已解决）

1. **Helena / wary 判据退化**：三条候选的 e2v disgusted 只有 0.02–0.03（P25 是法语片
   定的 0.005），等于没有区分度，只能当占位。Joseph 的 wary（1.00）和 Fielding 的
   （0.98 / 0.70）是真材实料。
2. **nervous 档普遍偏弱**：三人都只有 0.27–0.28。这条是数学硬顶 —— 紧张判据
   A×(1−D)，生成层 D≈A ⇒ 上限 0.25 左右，不是切片选差了。
3. **Fielding 音高偏低一档**：Lee Carter 是 14 岁演员，F0 197；Fielding 设定 8–11 岁
   （同片龄 Charles 294）。性格对（自信、贫嘴、语速快），年龄音色偏低。
4. ~~Joseph 无台词文本~~ **已解决**：补了 subf2m 的英文 BluRay 字幕（整体 −21s），
   15 条全部可读原文复核。上一版「只能听不能读」的问题不存在了。

## 六、怎么用

```bash
# 库自检（多角色通用）
python verify_lib.py --lib _emo_refs_all.json

# 闸门：多片合库必须带分域背景集
python dialog_gate.py --dir ch123_final --manifest _ch123_final.json \
    --lib G:/_setup/_emo_refs_all.json --bg-map "@G:/_setup/_bg_map.json"

# 单角色建库（同一套流程，可复用到任何新片）
python build_cast_refs.py --cand <候选> --role <角色> --per-slot 3 \
    --max-sil 0.52 --max-long-sil 1.2 --out _<角色>_refs.json
```

生产端取参考音只看「角色 + 情绪档」，不需要跨角色竞争 —— 所以合库对生成没副作用；
跨角色竞争只在「判说话人」时发生，那时必须带 `--bg-map`。

## 七、补字幕这条链（复用）

yifysubtitles 对 Hope Gap **只有西语**，别在那儿死磕。可用链路：

```
subf2m.co/subtitles/searchbytitle?query=<片名>      # 找 /subtitles/<slug>
subf2m.co/subtitles/<slug>/<lang>                   # 列条目，拿到 /subtitles/<slug>/<lang>/<id>
subf2m.co/subtitles/<slug>/<lang>/<id>/download     # 真下载地址（带 Referer 才给 zip）
```

同一部片常有多份（WEBRip / BluRay / HDRip），**timing 各不相同**，别按名字猜，
按下面两步定：

1. **ASR 词覆盖率扫描**：用现成音轨跑 300s 分块 ASR（只要词的时间，文本是不是英文都行），
   对字幕做 −90…+90s 偏移扫描，取覆盖率最高的偏移。
   Hope Gap 实测：Amazon −23.5s/97.1%、**BluRay −21.0s/98.3%**、HDRip −13.0s/98.2%。
2. **能量复核**：修正后 cue 窗应明显高于随机窗。同一片：0s 时 +0.2dB（等于没对上），
   −21s 时 **+3.6dB**。两条独立证据同向才动手切。

⚠ 生成修正字幕时别把时间轴行当正文写进去（第一版就是这么错的：正文 =
`00:04:35,492 --> 00:04:39,962 The surprisingly…`）。解析要按「找到含 `-->` 的行，
只取它**之后**的行」。

⚠ 还有个隐蔽坑：**课堂/群戏里的学生回答会被当成目标角色**。Hope Gap 的
"Less than 20,000 came back."（F0 191Hz）是学生说的，当时被选进了种子。
判据就是 F0：Edward 100–135Hz，超过 150 一律先怀疑。
