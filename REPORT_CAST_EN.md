# 英文片选角 → 下载 → 切角色音色（2026-11-08）

之前三个角色是从《我是城堡之王》**法语配音版**里切的。方向不对：那个片源只有
两个男孩 + 一个爸爸 + 一个妈妈，角色是被硬塞进已有桶里的。这次按正确顺序走：

**读简介/影评 → 找性格对得上、且观众认可演绎的角色 → 下载英文片 → 定位该角色 → 切参考音**

---

## 一、选角（依据影评原文，不是凭印象）

### Joseph Hooper（Hooper 他爸）→ 《Hope Gap》2019 / Edward / Bill Nighy

要求（`_corpus_plan.md` §6）：F0 110–130Hz、HNR 低、235–245 wpm、句内长停顿多；
检索词 `a hesitant middle-aged man, soft breathy voice, unsure`；难点是「犹豫」在朗读里没有。

选他的依据 —— Screen Daily 多伦多影评原话：

> **"Nighy gives a master class in withdrawn, mumbling ineffectualness — Edward is a spectral presence, even though he's very much alive."**

Rolling Stone 补了一条更关键的：

> "'The way I am seems to suit her,' he tells his son with rending simplicity."

「缩回去、嘟囔、没底气、总觉得自己错」—— 这就是 Joseph 的全部人格。而且这句台词是
**对儿子说的**，正好覆盖「对 Edmund 说话」的场景。影片本身是英国片（UK, 2018），
Edward 是历史老师，家里全是书，语域也贴。

### Helena Kingshaw（妈妈）→ 《Another Year》2010 / Mary / Lesley Manville

要求：谱质心 ≥1450Hz、240 wpm、句尾上扬；检索词 `a bright warm woman speaking eagerly, slightly breathless`；
难点是「用力推销自己」。

依据 —— IMDb 长评：

> "When she first enters the screen she looks like she's plugged to a nuclear power station — she just goes on and on and on, without running out of energy, **a chatterbox to end them all**. But this is all illusion. **She talks because she fears silence**, the emptiness."

A.V. Club：**"desperation and neediness roll off of her in thick, congealed waves."**
Empire：**"Manville should clear some shelf space for well-deserved awards."**

Helena 的核心不是「温柔妈妈」，是**用力过猛的乐观 + 怕冷场的话多 + 怕被看轻**。Mary 完全对上。

### Fielding（8–11 岁男孩）→ 《Son of Rambow》2007 / Lee Carter / Will Poulter

要求：与 Charles 同 F0 区、谱质心 >1830、**280+ wpm**；检索词 `a confident boy speaking quickly, clear voice`。
（**不是成年男性** —— 这条搞错过一次。）

依据 —— IMDb 影评：

> "**Poulter is hilarious in the role of Carter, delivering stinging wit and outraged putdowns with aplomb.**"

film.one：**"Poulter plays Lee as a bully who has worked out that bullying is quicker than asking."**
影片获 BAFTA 提名（3 项获奖 / 10 项提名），两个小演员的处女作被评 "remarkable debut actors"。

Lee Carter 是「自信、嘴快、爱命令人」的问题学生 —— 正是 Fielding 要的「a confident boy」。

---

## 二、下载：这一关是真实障碍，不是没找

### 2.1 YouTube「full movie」绝大多数是骗子（实测证据）

| 上传 | 时长 | 实测结论 |
|---|---|---|
| Son of Rambow "FULL MOVIE" | 97 min | 第 10 分钟后音频**全零**；第 50 分钟画面是一张海报 + `watch movie` 水印 |
| Secrets & Lies "Movie" | 136 min | 转写出来是**维基百科解说词**（"the film premiered on May 10, 1996 at the Cannes..."），不是台词 |
| Another Year × 3 个源 | 107/114/101 min | 正片 129 min，全对不上；上传者 `review_4u` 之类 |
| **Hope Gap "HD Movie"** | 100 min | **真片**（抽帧确认 Bill Nighy 在戏里，带宽 5520Hz@16k 正常） |

判定手法（不再靠标题猜）：
1. `ffmpeg` 抽一帧看画面（海报/文字版 = 假）
2. 逐 10 分钟统计 `>-40dB` 有声占比（有整段 0% = 假）
3. Whisper 转写（维基式旁白 = 假）

### 2.2 BT 被限速到不可用

- 直连：118 peer / 17 seed 也只有 **40–130 KB/s**（1.8GB 要十几小时）
- YTS 老片种子基本 **0 seed**（Son of Rambow、Another Year 的 720p/1080p 都是 0B）
- 想绕：`aria2 --all-proxy` **只管 tracker 不管 peer**；改用 `libtorrent` 开 SOCKS5 后
  peer 全部连不上（Clash 按域名分流，裸 IP:端口 的连接直接丢），换成 HTTP tracker 也一样

### 2.3 唯一能走快的是 HTTP

代理测速 **11 MB/s**（50MB / 4.5s）。所以只要拿到真实 HTTP 源，一百分钟片子 20 秒下完。
Hope Gap 就是这么拿到的。

---

## 三、已交付：Joseph（Hope Gap）

### 3.1 流程（新增三个脚本，都是通用件）

```
films/wav/hopegap.wav
  → film_seg.py      能量切句 925 段 + 声纹聚类
  → pick_cast.py     从指定簇里挑：纯度（防串音）+ 技术指标
  → who_is_who.py    每簇抽几条转写，靠文本点名
```

### 3.2 聚类结果（k=3 就干净）

| 簇 | 条数 | F0 中位 | 判定 | 依据 |
|---|---|---|---|---|
| 2 | 430 | 117 Hz | **Edward** | 第一条出现在 **1.8s**（开场就是他和 Grace 在厨房），且与女声簇共现于争吵戏 |
| 0 | 386 | 169 Hz | Grace | 成年女 |
| 1 | 109 | 99 Hz | Jamie | 第一条出现在 **1029s（17 分钟）**，正好是儿子回家那场 |

### 3.3 参考音库 `_joseph_refs.json`（5 档）

| 档（按可测韵律命名） | 起点 | 时长 | F0 | F0 sd | 纯度 |
|---|---|---|---|---|---|
| soft_long | 3762.0s | 7.7s | 102 | 20.0 | 0.72 |
| soft_long | 4849.0s | 6.6s | 95 | 18.1 | 0.62 |
| long_animated | 3595.8s | 7.6s | 96 | 29.9 | 0.70 |
| high_var | 253.6s | 7.7s | 132 | 34.4 | 0.68 |
| clean_mid | 2793.3s | 4.0s | 110 | 21.3 | 0.73 |

- 227 / 259 条候选过了硬检查（纯度 ≥0.12、有声占比 ≥55%、首尾不掉 >35dB）
- **留一法 5/5**，最差一对余弦 **0.484**（阈值 0.35）→ 确认同一人，没有串进 Grace/Jamie

**注意**：档名是「可测的韵律特征」，不是语义标签。soft_long / high_var 这些要**听完再改名人设**
（犹豫 / 拔高 / 疲惫 / 对儿子说话）。不听完就贴"虚张声势"是编的。

---

## 四、还差的两个人

Helena 和 Fielding 的选角和依据都定了，卡在片源：

- 《Another Year》2010 —— YTS 老种 0 seed，YouTube 无真片
- 《Son of Rambow》2007 —— 同上（8 seed 的 720p 连不上任何 peer）

三条可行路径（按省事排序）：

1. **你丢片子**：把两个 mkv/mp4 放进 `G:/NEW MOVIE`，我这边一条命令跑完
   （`film_seg` → `pick_cast` → 建库 → 留一法），不需要字幕
2. **走你的下载通道**（迅雷/PT/seedbox）拿到文件，同上
3. **换更容易拿到的片**，但人选要重挑 —— 性格对不对得上比下载方便重要，我不建议为省事换

另：如果这两个角色的目标语域和 Hope Gap 差太远（比如 Helena 要 cockney），
选角可以再议 —— 现在选 Mary 是伦敦中产口音，跟「寡妇做管家」的身份是贴的。
