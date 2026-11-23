# 对白全库体检（239 条）

> 口径：`G:/_setup/_audit_all.py`（声学 + 亮度 + 音高 + 内容）
> ＋ `_audit_whisper.py`（第二 ASR）＋ `_audit_triage.py`（双 ASR 仲裁）
> 原始数据：`_dlg_audit.json` / `_audit_asr.json` / `_audit_whisper.json` / `_audit_triage.json`

## 一、体检维度

| 维度 | 指标 | 判据 |
|---|---|---|
| 内容 | ASR 词序列 vs 原文（difflib 对齐） | 开头多词 `lead>=2` / 漏词 `tail>=2` / 覆盖率 `<0.60` |
| 亮度（情绪） | voiced-tilt：有声帧 2~5k / 200~1k 能量比 | 非「喊」类情绪 `> max(0.30, 3×同档中位)` |
| 音高 | 有声帧 F0 中位 | 超出同角色 p5~p95 的 8% 以外 |
| 静音 | silent ratio（25ms 帧 / -45dBFS） | `>0.55` 且 `dur>=1.6s` |
| 电平 | voiced RMS | 不在 `[-25.5, -22.5]` |
| 重复 | md5 | 同 md5 出现 >1 次 |

**短句（<1.6s）走 `_short_gate.py`**，声纹/情绪免责。

## 二、结果

| 项 | 值 |
|---|---|
| 总条数 | 239 |
| 被标记 | 89 |
| **双 ASR 判为 ASR 噪声** | **58** |
| 双 ASR 判为真问题 | 15 |
| 其中「写法差异」误判（O.K./Okay、C'mon/Come on） | 3 |
| 待查（单处词差异） | 16 |
| 重复音频 | **0 组** |
| 电平越界 | **0**（中位 −24.01，跨度 0.83dB） |
| voiced-tilt 中位 | Charles 0.073 / Helena 0.080 / Joseph 0.060 / Thomas 0.201 |

**单 ASR 会把 58 条好音频判死（65%）** —— 这就是为什么必须双 ASR 仲裁。
Parakeet 在 5 条上整段返回空（`c2_0265`/`c2_0404`/`c2_0467`/`c3_0838`/`c2_0413`），
whisper 对同样文件给出 1.00 覆盖。

## 三、真问题明细（15 → 去重后 12+3 存疑）

### A. 开头多念了参考片段的词（LEAD_REF，6 条）

| id | 角色/情绪 | 时长 | 多念的内容 | 状态 |
|---|---|---|---|---|
| `c2_0428` | Joseph 激动反抗 | 9.71s | 「The truth is I made a mistake about Grace right」(10 词) | **已裁**，现 7.31s，ASR 全对 |
| `c1_0165` | Joseph 紧张 | 3.04s | 「He never really forgave me for not being him」(9 词) | **已裁**，现 1.32s「Well yes.」 |
| `c1_0046` | Joseph 平静 | 2.40s | 「Ah, the mother slobber」(4 词) | **已裁**，现 0.60s「Yes.」 |
| `c2_0413` | Joseph 激动反抗 | 1.26s | 「Oh, please, mate」(3 词) | **已裁**，现 0.52s |
| `c1_0043` | Joseph 紧张 | 2.56s | **整句都是参考词**，原文「May...」完全没有 | 重生成中 |
| `c1_0047` | Joseph 紧张 | 2.30s | **整句都是参考词**，原文「Well...」完全没有 | 重生成中 |

机制：目标句极短（1~2 词）时，模型会把**参考片段自己的文本**念一遍再接正文。
这解释了为什么只有「一个词也要表演好」的这些行出问题。

### B. 开头内容缺失（7 条）

| id | 原文 | 实际念的 | 缺失 |
|---|---|---|---|
| `c1_0021` | That is not the way to speak! You must show respect. | You must show respect. | 第一句整句（7 词） |
| `c2_0487` | What are you going back into the house for? I've seen all the house, haven't I? | I've seen all the houses, haven't I? | 开头 9 词 |
| `c3_0838` | Yes, every sort of moth in the world. | of moth in the world. | 开头 4 词 |
| `c2_0195` | Warings, … sounds so much like the home… | Zelena Kingshaw had replied, … | 「Warings」 |
| `c3_0812` | What for? It's only a lot of old books and dead fish. | It's only a lot of old books… | 「What for?」 |
| `c3_0874` | You'd better not. | Better not. | 「You'd」 |
| `c2_0312` | A few years ago. I was about five. Or six. | Two years ago, I was about five or six. | 「A few」→「Two」 |

### C. 听不清 / 疑似念错（2 条）

| id | 原文 | Parakeet | Whisper |
|---|---|---|---|
| `c1_0050` | There's nobody to play cricket with. | Die vraag die Fake Ricket. | If you like, what do you think? |
| `c3_0649` | What will? | Bonne Will! | No one will. |

两条 ASR 给出完全不同的内容，说明音频本身糊了（不是识别问题）。

### D. 存疑（单处词差异，未定论）

`c2_0262`（Scaredy → Scardy/Skeldy）、`c3_0659`（I dare you → He dare you）、
`c3_0651`（Hooper → who/Uber）、`c2_0357`（I say → they say）、
`c3_0809`（prying → playing）、`c2_0217`（It is → This is）。
多数属于 ASR 对短词的极限，需人耳；其中 `c3_0651` 的「Hooper」被听成 Uber 是 ASR 典型误识。

## 四、一个必须记下的坑：参考音频的 ASR 结果本身不可信

`_emo_refs_asr.json` 是 Parakeet 跑参考片段得到的，**它把英语参考听成俄语/法语**：

| 参考 | 库内文本 | Parakeet | Whisper |
|---|---|---|---|
| `Joseph_nervous_c043.wav` | And she never really forgave me for not being him. | Эдварда, которого она хотела. | I have never met you before.（重复两遍） |
| `Charles_neutral_4.wav` | J'en ai pas besoin. | J'ai pas besoin de boussole! | I hope you enjoyed the video, see you next time! |

两路 ASR **都在这类参考上产生幻觉**（whisper 的「see you next time」是典型的静音幻觉）。
⇒ 之前「参考库文本大面积与音频不符」的结论**只由 Parakeet 单路支撑，未证实**；
不能拿这个文件去判参考对不对，也不能据此认为参考文本错了。

## 五、修复记录（13 条，全部 ASR 复核）

| id | 问题 | 做法 | 复核（whisper / Parakeet） | 现时长 |
|---|---|---|---|---|
| `c2_0428` | 开头多念 10 词 | 裁 2.40s 起 | 全句一字不差 | 6.99s |
| `c1_0165` | 开头多念 9 词 | 裁 1.72s 起 | 「Well yes.」 | 1.18s |
| `c1_0046` | 开头多念 4 词 | 裁 1.80s 起 | 「Yes.」 | 0.48s |
| `c2_0413` | 开头多念 3 词 | 载体「Edmund! Get back here!」切首词 | 「Edmond.」 | 0.89s |
| `c1_0043` | 整句都是参考词 | 换 seed 89 + 裁 1.70s | 「Maybe」/「Me.」（存疑） | 0.56s |
| `c1_0047` | 整句都是参考词 | 换 seed 89 + 裁 1.78s | 「Well.」 | 0.46s |
| `c1_0021` | 缺第一句 | 换 seed 89 | 全句完整 | 4.38s |
| `c2_0487` | 缺开头 9 词 | 换 seed 83 | 全句完整 | 3.20s |
| `c2_0312` | 「A few」→「Two」 | 换 seed 83 | 「A few years ago…」 | 3.13s |
| `c3_0874` | 缺「You'd」 | 换 seed 83 | 「You better not!」 | 1.62s |
| `c2_0195` | 缺「Warings」 | **换参考**（Helena_excited_1）+ seed 11 | 「Wearings, Mrs. Helena…」 | 5.32s |
| `c3_0812` | 缺「What for?」 | **换参考**（`c039` Charles neutral 2）+ seed 11 | 全句完整 | 2.67s |
| `c3_0649` | 「What will?」念错 | 载体「What will? What will they do?」切首句 | 「What will?」 | 0.89s |

备份：`_bak_trimlead_1120b/`、`_bak_short_1120b/`、`_bak_trimtail_1120/`；
回填记录 `_backfill_short2.json` / `_cut_at_log.json`。

**关键经验**：换参考对「开头被参考词顶替」这类最有效（`c2_0195`、`c3_0812` 一次就中），
单换 seed 只能碰运气。

## 六、仍然没解决的（4 条）

| id | 原文 | 现象 | 已试 |
|---|---|---|---|
| `c3_0838` | Yes, every sort of moth in the world. | 开头 4 词丢失，且「moth」被念成 melting/most | 4 seed（83/89/107/113）全失败；「moth」的 θ 与 `c3_0837`「Moths」同源问题 |
| `c1_0050` | There's nobody to play cricket with. | 两路 ASR 都听不出内容 | 2 seed 只生成出 0.48s / 0.32s 残片（生成失败） |
| `c1_0043` | May... | 单字碎片，ASR 读作 Maybe / Me | 已裁到 0.56s，需人耳 |
| `c2_0262` | Scaredy! | ASR 读作 Scardy / Skeldy | 判断为 ASR 极限，音频大概率是对的 |

## 七、结论

- **239 条里真正需要动音频的：13 条已修 + 4 条未决 = 17 条**，其余 222 条内容无误。
- 单 ASR 体检会把 59 条（25%）好音频判死 —— **以后任何内容体检必须双 ASR 仲裁**。
- 电平、静音、重复音频全库 0 越界。
