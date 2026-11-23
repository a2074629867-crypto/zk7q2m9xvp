# 三个缺档角色的参考音：自动切 + 冷启动补库

> 2026-11-08。对象：`_voice_profiles.md` §0 表里三个「0 档」的角色
> —— Joseph Hooper、Helena Kingshaw、Fielding。

---

## 一、先说结论

| 角色 | 结果 | 来源 | 状态 |
|---|---|---|---|
| **Joseph Hooper**（Hooper 他爸） | 5 档 | 《我是城堡之王》原片 | 可用 |
| **Helena Kingshaw**（妈妈） | 4 档 | 《我是城堡之王》原片 | 可用 |
| **Fielding**（菲尔丁） | 3 档 | 换片 *Millions* (2004) | 可用但**语速/性格只一半达标** |

自动切法本身是通的，但**补角色音色不能从「判角色」入手** —— 原因见 §2。

---

## 二、为什么必须先聚类

1-NN 判角色必须有模板。没模板的角色不会输出「未知」，而是被硬塞进已有的桶。
实测现在这套库（只有 Charles / Thomas 两个男孩）跑全片 257 条 cue：

```
Thomas 193 条 / Charles 64 条 / 其他 0 条
```

成年男（Joseph）和成年女（Helena）一条都没单独出来 —— 他们的声音被强行
分给了两个男孩。**这不是阈值问题，是模型结构问题：判据是「最像谁」，
而不是「像不像人」。**

所以补角色音色的第一步是**不看角色、只按声音聚类**。

---

## 三、本片实际有几种人声

`voice_cluster.py` 对 257 条 cue 做余弦层次聚类：

| k | 分出的簇（条数 / F0中位 / 声部） |
|---|---|
| 2 | 191 / 228Hz / 界(女童)　66 / 82Hz / 成年男 |
| **3** | **158 / 242Hz / 儿童**　**66 / 82Hz / 成年男**　**33 / 195Hz / 成年女** |
| 4 | 158 / 儿童　64 / 82Hz 成年男　33 / 195Hz 成年女　**2 / 139Hz 成年男** |
| 5–6 | 再拆只多出 2–5 条的碎片，无新增说话人 |

**k=3 就干净了。** 多出来的 2 条（c392/c393，组内余弦 0.584）是片中
「站直，别动，1、2、3」的**摄影师**，只出现一次。

⇒ 《我是城堡之王》全片只有 3 类人声：2 个男孩（同一簇，需再分）、
Joseph、Helena。**Fielding 在这部片里没有素材**（不是没切到，是没这个人）。

---

## 四、Joseph 与 Helena：簇 → 角色怎么确认

聚类只给出「这簇是成年男」，不给名字。命名靠**读字幕文本**：

**簇 0（82Hz，64 条）→ Joseph**
- 「我要雇那个女管家，她有个跟你同岁的儿子」→ 对儿子说话、鳏夫身份
- 「您见不到 Thomas，他有点不舒服」→ 对客人客套（假权威）
- 「光这条道上我就损失了 300 多棵百年山毛榉」→ 用废话填尴尬

**簇 2（195Hz，33 条）→ 妈妈**
- 「你要好好照顾他，宝贝」
- 「Charles……」
- 「我明天收拾行李」

⚠️ 簇 0 里混了**神父**的弥撒祷告（c059–c063，"Seigneur/pain/siècles"），已按文本剔除。

### 4.1 声纹自检（能不能用）

| 组 | 组内余弦中位 | 范围 |
|---|---|---|
| Joseph | **0.405** | 0.245–0.523 |
| Helena | **0.380** | 0.377–0.419 |
| 儿童（混合两人） | 0.049 | −0.145–0.142 |
| Joseph vs Helena | 0.014 | — |
| Joseph vs 儿童 | 0.031 | — |
| Helena vs 儿童 | 0.141 | — |

组内 0.38–0.41 远高于跨组 0.01–0.14，**分得开**（阈值线 0.35）。
儿童组内只有 0.049 是因为那一簇混了 Charles 和 Thomas 两个人。

### 4.2 留一法

拿掉一条、用同角色其余条当模板判它：**9/9 全对**。

| 档 | 出处 | 时长 | 组内最近 | 跨角色最高 |
|---|---|---|---|---|
| Joseph/normal | c046 | 4.2s | 0.523 | 0.036 |
| Joseph/ramble | c048 | 5.6s | 0.670 | 0.107 |
| Joseph/sigh | c049 | 3.3s | 0.670 | 0.056 |
| Joseph/angry | c326 | 4.2s | 0.501 | 0.157 |
| Joseph/panic | c146 | 4.6s | 0.501 | 0.202 |
| Helena/bright | c370 | 7.8s | 0.328 | 0.139 |
| Helena/sweet | c318 | 7.3s | 0.383 | 0.202 |
| Helena/scold | c336 | 4.9s | 0.383 | 0.146 |
| Helena/care | c366 | 4.7s | 0.317 | 0.052 |

### 4.3 档位对应设定

**Joseph**（虚张声势的空心大人）

| 档 | 台词 | 对应设定 |
|---|---|---|
| normal | «Mais d'ici, on ne la voit pas, car il y a toujours de la brume.» | 客套解说 |
| ramble | «…j'ai perdu plus de 300 hêtres, tous centenaires.» | **用废话填尴尬** |
| sigh | «Ç'a été un grand malheur.» | 叹气 |
| angry | «Je t'ai dit de disparaître. Tu entends, Thomas?» | **突然抬高音量**（F0 323） |
| panic | «Ne partez pas! Vous ne pouvez pas partir!» | 底气不足的哀求 |

**Helena**（以爱为名的情感绑架者）

| 档 | 台词 | 对应设定 |
|---|---|---|
| bright | «Allez, viens. On va danser.» | **用力过猛的乐观** |
| sweet | «Viens, Charles. On rentre à la maison.» | 甜而居高 |
| scold | «Non! Je ne veux pas te voir avant demain! Mets-toi au lit…» | 施压时的硬 |
| care | «Il faut s'amuser. C'est ton dernier dimanche avant le collège.» | 关切的推销感 |

---

## 五、Fielding：本片没有，换片也只能算半个

### 5.1 先纠正一个前提

`_corpus_plan.md` §6 写的是：与 **Charles 同 F0 区** / 谱质心 >1830 /
**280+ wpm** / 首选源 **MyST（8–11 岁）+ CSLU Kids** / 检索词 *a confident boy*。

**Fielding 是男孩，不是成年男性。** 这条如果搞错，选片方向会整个反。

### 5.2 片源筛选

《我是城堡之王》无此人。翻本机片库，按三条硬标准选：

1. 音质带宽 ≥5kHz（踩过 Careful 1983 的坑：3541Hz，声纹 AUC 0.482 = 随机）
2. 有 8–11 岁、话多、自信的男孩
3. 字幕带说话人标记（等于免费真值）

选中 ***Millions* (2004, Danny Boyle)** —— Damian 是 7 岁英国男孩，爱说话、
想象力足。

| 指标 | Millions | 城堡（参照） | Careful 1983（失败案例） |
|---|---|---|---|
| 累计 95% 带宽 | **6426 Hz** | 6245 Hz | 3541 Hz |
| 4kHz 以上能量 | **18.8%** | 4.0% | 0.5% |

音质比城堡还好，**不是瓶颈**。

### 5.3 字幕标记这条路只走了一半

全片 1762 条 cue，带 `NAME:` 标记的只有 **108 条（6%）**：

```
ANTHONY 25 / DAMIAN 19 / RONNIE 12 / WOMAN 6 / MAN 5 / NARRATOR 5 / DOROTHY 5
```

### 5.4 语速实测

| 说话人 | 最快 | 常见区间 | 能否达 280wpm |
|---|---|---|---|
| **ANTHONY**（哥哥） | **367 wpm** | 180–277 | **能**（1 条） |
| DAMIAN（弟弟） | 232 wpm | 120–210 | 不能 |

菲尔丁要「快」，只能取哥哥 Anthony。

### 5.5 声纹自检抓出误标

初选 5 条，两两余弦：

```
F_direct – F_flat     0.850
F_fast   – F_flat     0.679
F_fast   – F_direct   0.604
F_confident – 其余     0.050 ~ 0.151   ← 不是同一个人
F_sharp     – 其余     0.151 ~ 0.281   ← 也不像
```

**字幕标 ANTHONY，但 c17/c1 实际不是他说的**（或该 cue 混了两人）。
这是「字幕时间轴 ≠ 说话人边界」的同一个坑，第二次踩到。

只保留声纹确认同人的 3 条：

| 档 | 台词 | 时长 | 语速 |
|---|---|---|---|
| Fielding/fast | «So what are we going to do with it, then?» | 1.6s | **367 wpm** |
| Fielding/direct | «Where are you gonna find poor people?» | 2.1s | 203 wpm |
| Fielding/flat | «Right, that's enough messing around.» | 1.7s | 180 wpm |

### 5.6 只达标一半，如实说

- ✅ **语速**：367 wpm 那条正好卡在要求线上
- ❌ **性格**：Anthony 是「算计、贪心的哥哥」，快而冲，**不是「阳光、没心没肺」**
- ❌ **档位少**：3 档，且没有「阳光 / 开心」这一档

如果菲尔丁在书里是开心果型，这个音色会偏冷。要真到位得换一部
**主角本身就是阳光话多男孩**的片（*Son of Rambow*、*The Kid Who Would Be King* 这类），
本机没有。

---

## 六、并入主库会不会破坏现有判定

把 Joseph + Helena 加进主库（25 → 34 条模板），回放 59 条成品：

| 方案 | PASS | PASS 纯度 | 总准确率 |
|---|---|---|---|
| 原库（只有两个男孩） | 38 | 100% | 86.4% |
| 四角色库（+Joseph +Helena） | 38 | 100% | 83.1% |

PASS 和纯度都没动，但准确率掉 3.3 个点。原因是 2 条变了：

| 条 | 真值 | 原库 | 四角色库 |
|---|---|---|---|
| L071 | Charles | Charles +0.66 | **Helena** −0.01 |
| L078 | Charles | Charles +0.30 | **Helena** −0.30 |

两条都是 Charles 的**轻声软句**，被成年女模板吸走 —— 轻声时 F0 塌到女声区、
声纹特征又弱，两个维度都不可靠。

⇒ **按用途分库，不合并**：
- 男孩成品验收 → `_emo_refs.json`（现状）
- 成年角色 / 新片 → `_emo_refs_v2.json`

`dialog_gate.py --lib` 已经支持切换，不需要改代码。

---

## 七、顺带纠正的一个长期误会

法语配音版**改了名字**，对不上英文原著：

| 英文原著 | 法语版 |
|---|---|
| Edmund Hooper | **Thomas** |
| Helena Kingshaw | **Mme Vernet** |
| Charles Kingshaw | Charles（保留） |

依据：神父祷告词「Bénissez aussi, Seigneur, **Mme Vernet et son fils Charles**」；
仆人线「Vous ne verrez pas **Thomas**」。

所以模板库里那个叫 `Thomas` 的角色，一直是 **Edmund**。之前所有报告里的
「Thomas 短板」实际指的都是 Edmund。**不改库（会连锁影响文件），但写在这里备查。**

---

## 八、文件

| 文件 | 内容 |
|---|---|
| `voice_cluster.py` | 无监督分人声（聚类 + F0 声部判定） |
| `adult_refs.py` | 聚类 → 筛干净句 → 点名校 → 建库 + 留一法 |
| `refs_adult/` | 12 个 wav（Joseph 5 / Helena 4 / Fielding 3） |
| `_adult_refs.json` | Joseph + Helena 库 |
| `_fielding_refs.json` | Fielding 库（Millions） |
| `_emo_refs_v2.json` | 四角色合并库（对照用，非默认） |
| `out/voice_cluster.json` | 257 条 cue 的簇归属 + F0 |
| `_millions/` | Millions 全片音轨、Damian/Anthony 台词与切条 |

## 九、还没解决

- **Helena 只有 4 档、且组内余弦 0.32–0.38 偏低**（女性情绪方差 > 说话人方差）。
  要稳得再补 3–4 条。
- **Fielding 语速只有 1 条达标**，性格不对。需要换一部主角是阳光快嘴男孩的片。
- 本片成年男只有 66 条、成年女 33 条，**按字幕切条后能用的完整句只有 13 / 7 条**
  （其余跨两句或停顿过长）。要更多素材得改切条策略，不是加片长。
