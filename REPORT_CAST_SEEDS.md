# 用「选角」的方式补角色音色（Lee Carter / Mary）

> 2026-11-08 ~ 11-09。用户的要求原话：
> 「根本不是法语片里切啊，是英国的电影里，看简介或者评论，先找到性格合适，观众也觉得演绎合适的
> 角色，然后自己下载电影音频，找到对应人物切，我说的三个人物都是得这样切。」

这条路线和之前「拿一部片子从头切到尾」的区别：**先定角色，再下片，再定位**。
角色选择的依据是性格（读者/观众对这个角色的印象），不是「片里声音分几簇」。

---

## 1. 结果先看

| 目标角色 | 替代方案 | 片源 | 库 | 留一法 |
|---|---|---|---|---|
| Fielding（8–11 岁男孩，280+ wpm，*a confident boy*） | **Lee Carter** / Will Poulter | Son of Rambow 2007（英） | `_fielding_refs.json`，5 档 10 条 | **10/10** |
| Helena / Mme Vernet（成年女） | **Mary** / Lesley Manville | Another Year 2010（英） | `_helena_mary_refs.json`，5 档 10 条 | **10/10** |
| Joseph（成年男，已交付） | Edward / Bill Nighy | Hope Gap 2019 | `_joseph_refs.json` | 5/5 |

四角色合并库 `_emo_refs_all.json`（45 条模板）交叉验证：

- Fielding 留出 6 条 → **6/6** 判回 Fielding
- Helena 留出 6 条 → **6/6** 判回 Helena
- Charles 10 条 → 9/10（唯一失手是 1.6s 的短句，0.48 被 Fielding 吸走）
- Thomas 15 条 → **15/15**

---

## 2. 片源与验真

| 片 | 大小 | 时长 | 音轨 | 字幕 |
|---|---|---|---|---|
| Son of Rambow 2007 720p | 938MB | 1:35:07 | 5.1 → 取 FC | **内封英文字幕**（mov_text，79KB） |
| Another Year 2010 1080p | 2.66GB | 2:09:47 | 5.1 → 取 FC | 无内封 |

验真（YouTube「full movie」假源踩过两次，这步不能省）：

- 抽帧：Rambow 300s 是学校挂「法国朋友来访」横幅、3600s 是 Lee Carter 特写；
  Another Year 2400s 是 Jim Broadbent 的餐桌场景 —— 都对得上剧情
- 时长与 bitrate 正常（1314 / 2730 kb/s），不是静态图

**踩坑：音轨必须取中置声道。** 直接把 5.1 平均成单声道，对白被摊薄到
RMS −42dB，VAD 判成静音（实测种子句 88% 判静音、语速算出 20 词/秒的鬼数字）。
`pan=mono|c0=FC` 之后 −34dB，再按峰值归一到 −1dBFS。

**踩坑：外部字幕可能对不上版本。** Another Year 从 yifysubtitles 拿到的英文 srt
结束在 2:00:45，而手里蓝光版 2:09:47（差 9 分钟，不同剪辑）。按 cue 窗口测能量
也证明对不齐（cue 窗 −39.3dB vs 随机窗 −42.0dB，只差 2.7dB）。
⇒ 换 `film_asr.py` 从音频本身生成时间轴（parakeet-tdt-0.6b-v3 int8，RTF 0.07，
2 小时片 27 分钟）。

---

## 3. 为什么不能靠聚类找角色

Rambow 751 条 cue 做无监督聚类（k=2..7）：

```
k=4  635/218Hz 成年女   112/109Hz 成年男   3/165Hz   1/140Hz
```

**635 条挤在一簇** —— 声纹模型主要在成人数据上训练，同片同龄儿童分不开。
Another Year 也一样：k=5 分出 493 女性 / 268 男性，但两位成年女（Mary 与 Gerri）
再怎么拆都是 619/14、296/12 这种退化结果。

⇒ 改成 **种子扩增**（`cast_from_seed.py`）：

1. 读字幕文本 + 时间点，人工确认 5–10 条「这个人说的」
2. 用这几条算声纹质心，对全片求余弦
3. 硬检查（混人 / 音效 / 太短 / F0 越界）后按相似度排
4. 留一法验证种子内部一致性（<0.35 说明种子选错了句子）

这个方法的基础是**文本可复核**：扩出来的每一条都能回看原文确认是不是他说的。

### 种子怎么定

**Lee Carter**（513.5–557.8s 走廊那场，连续 9 句都是他）：
```
Listen, mate, I don't mind taking the blame for this if you like.
Fair enough. I always fancied a watch.
Didn't you know? About the torture?
```
留一法 min 0.509 / 中位 0.773 → 阈值 0.409，扩出 45 条，全是他的台词
（"you'll be the stuntman in the film I'm making"、"My dad? No. He pissed off
before I was born"、"I swear to God, if you tell anyone I'm making this film"）。
唯一混进来的 `Will Proudfoot.`（0.598）是另一个男孩答名字，被阈值挡在外面。

**Mary**（6 句自述型独白，读者一眼能认）：
```
838.7  and I looked out the window and I saw these two little daffodils peeping...
3123.0 I got it ever so cheap I was really tough with myself because they wanted 700
3815.2 I'm very much a glass half fool kind of girl
4609.8 ...the guy kept trying to touch me and it cost me nearly five hundred pounds
```
留一法 min 0.708 / 中位 0.765 → 阈值 0.608，扩出 60 条，全是她的抱怨、
买车、离婚、怕一个人过周末。**这一步同时证明了两件事**：种子没选错，且
Another Year 里两位女性可以被「内容」分开（聚类分不开，文本分得开）。

> 判据：Mary 的台词第一人称密度极高（我、我的、我一个人）。Gerri 是心理咨询师，
> 说话是「问句 + 复述对方」。按这个读，49 条一眼能分。

---

## 4. 情绪分档

`emo_cut.py --no-role --e2v` 给每条算五类判据，再 `trim_cues.py` 裁掉字幕窗口
多余静音（**字幕 cue 的窗口普遍比台词宽**：54 条候选里 19 条静音占 55–85%）。

裁边口径与 `film_seg.py` 一致：帧长 25ms / 帧移 10ms，阈值
`max(底噪 p20+6dB, 峰 p95−30dB)`，取首尾有声帧，前后留 50ms。

`build_cast_refs.py` 逐档挑条，四道门：硬检查 → 未在别档用过 → 时长 2–9s →
同档不重复。

### 建库结果

| 角色 | 兴奋 | 激动反抗 | 委屈 | 警惕 | 紧张 |
|---|---|---|---|---|---|
| Fielding | 0.43 / 0.40 | 0.70 / 0.69 | 0.79 / 0.74 | 0.98 / 0.70 | 0.28 / 0.27 |
| Helena | 0.62 / 0.58 | 0.69 / 0.68 | 0.81 / 0.59 | 0.03 / 0.02 | 0.27 / 0.27 |

（数字是该条在该判据上的值，每档 2 条）

F0 对照：

| 角色 | F0 中位范围 | 说明 |
|---|---|---|
| Fielding (Lee Carter) | 182–280（中位 196） | 14 岁演员演 11–12 岁角色 |
| Helena (Mary) | 152–348（中位 223） | 成年女，情绪起伏大 |
| Charles（法语片，8 岁） | 173–422（中位 294） | 真儿童 |
| Thomas（法语片，10 岁） | 162–368（中位 213） | |

---

## 5. 必须说清的两个不确定项

**① Fielding 的音高可能偏低。** Lee Carter 是 Will Poulter 14 岁演的，F0 中位 196；
而 Fielding 是 8–11 岁，法语片里同龄的 Charles 中位 294。性格（自信、贫嘴、语速快）
对得上，**年龄音色偏低一个档**。要更贴的话，同一个片子里还有 Will Proudfoot
（Bill Milner，拍片时 11–12 岁，音更高但性格是腼腆型）。

**② 「警惕」判据在这两个演员身上退化。** Mary 五条候选全是 0.02–0.03
（P25=0.005 是拿法语片素材定的），等于这一档没有区分度。Fielding 有一个 0.98
（"their bone goes up through their brain and kills 'em"）是真材实料。
⇒ 警惕档在有 0.98 的那条时可信，其余当作占位。

---

## 6. 新增脚本

| 脚本 | 干什么 | 为什么单独写 |
|---|---|---|
| `cast_from_seed.py` | 种子 cue → 全片扩增同一个人 | 聚类对同龄儿童无效，只能从可复核的文本种子出发 |
| `film_asr.py` | 无字幕片 → 逐句时间轴（parakeet int8） | 外部字幕经常对不上版本，只能从音频生成 |
| `trim_cues.py` | 裁掉字幕窗口的多余静音并重算 sil / wps | 带 80% 静音的参考音会摊薄 embedding、还会把 `1−A` 刷高 |
| `build_cast_refs.py` | 候选表 → 按情绪档建库 + 留一法 | 直接取 top1 会拿到重复素材和半句 |

复用：`cut_cues.py`（切条）、`voice_cluster.py`、`emo_cut.py`、`chain_check.EmoVoice`。

---

## 7. 复现命令

```bash
PY=/g/Python310/python.exe
FF=/e/tool/ETS/ffmpeg/ffmpeg.exe

# 取中置声道 + 归一化（对白在 FC，5.1 平均会把对白摊薄到 −42dB）
"$FF" -i film.mp4 -vn -af "pan=mono|c0=FC" -ar 16000 -c:a pcm_s16le -y film_fc.wav

# 有内封字幕：直接提；没有：ASR 生成
"$FF" -i film.mp4 -map 0:s:0 -c:s srt -y film.srt
/g/_setup/asr_venv/Scripts/python.exe film_asr.py --wav film_fc.wav --out film_asr

# 切条 → 读文本定种子 → 扩增 → 情绪打分 → 裁边 → 建库
$PY cut_cues.py --video film_fc.wav --srt film.srt --out cues --max-dur 12
$PY cast_from_seed.py --cues cues --seeds 513.5,518.6,525.6 --out cast --top 60
$PY emo_cut.py --cues cues_sel.json --out emo --no-role --e2v --top 8
$PY trim_cues.py --cand emo/candidates.json --outdir emo/trim --out emo/cand_trim.json
$PY build_cast_refs.py --cand emo/cand_trim.json --role Fielding \
    --src "Son of Rambow 2007 / Lee Carter / Will Poulter" \
    --out _fielding_refs.json --max-sil 0.52 --max-long-sil 1.2 --other _emo_refs.json
```

产物目录：`G:/MOVIE_DL/`（`_cues_*`、`_cast_*`、`_emo_*`、`_wav/`），
库文件与音频在 `G:/_setup/_fielding_refs.json`、`G:/_setup/_helena_mary_refs.json`、
`G:/_setup/refs_cast/`。
