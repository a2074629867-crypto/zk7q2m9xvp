# 旁白停顿语义标注（马修母带，盲标）

这是三方交叉验证中的一票。**独立判断，不要猜测"标准答案"。**

## 背景

素材是《Wonder》有声书的旁白朗读（男声，睡前故事语调，107wpm）。
每一条给出一段连续文本，中间用 `[PAUSE]` 标出**一处真实存在的停顿**。
你的任务：判断这处停顿在**语义结构**上属于哪一类。

**注意：不要猜停顿有多长。** 我们刻意没给时长——给了就会锚定。
你只判结构，时长由我们事后按类别统计。

## 标注档位

| kind | 判据 |
|---|---|
| `drop` | **完全不停也不影响理解。** 四种情况：<br>① 语法性逗号（`like` `as` `than` `that` 前后是同一语法单元）<br>② 填充词/呼语后紧接主句（`Well` `Now` `And` `Oh`）<br>③ 反意疑问结构内部的插入成分（`..., then, shouldn't he?` 里的 then）<br>④ 连续短项列举 |
| `tight` | **只停半拍（0.15~0.25s），且停顿后这句话还没说完。**<br>① 插入语/补充说明（`he was twenty,` 后面接主句）<br>② 从句没说完，后面还有主句成分<br>③ 修饰语与中心词之间（`a memory [PAUSE] of a boy`）<br>**⚠ 句末不能用 tight。** 后面接新句子就必须是 clause 以上 |
| `clause` | **正常分句边界（0.4~0.6s）。这是句末的默认值。**<br>① 两个完整分句之间（各有主谓）<br>② 并列/转折/定语从句连词之前（but / and / so / because / which） |
| `beat` | **情绪/信息落点（0.6~0.8s）。三条必须同时满足：**<br>① 停顿前那一段是完整、有分量的话（不是从句、不是半句）<br>② 停顿后接的是回应/结论/新信息，不是继续同一句<br>③ **把停顿缩到 0.2s，这句话的力度会明显损失**<br>（第③条是硬标准：如果你觉得缩短了也没差，那就不是 beat） |
| `paragraph` | **段落级（≥1.5s）。**<br>① 话题/场景切换　② 时间或地点跳转　③ 视角转换（叙述→内心独白） |

**判定顺序（不许反，每条按顺序问一遍）：**

1. **完全不停会不会听不懂？** 不会 → `drop`
2. **停顿后这句话说完了吗？** 没说完 → `tight`
3. **是不是换话题/换场景/换视角？** 是 → `paragraph`
4. **beat 的三条硬判据都满足吗？** 满足 → `beat`
5. 剩下全是 `clause`

> 上一轮 16 条对白的三方标注 Kappa 只有 0.61，分歧全在 tight 和 beat 上：
> 有人把句末判 tight、有人把句末一律判 clause。
> 所以这一版把「句末不能用 tight」「句末默认 clause」写死了。

## 反例（容易标错）

- `as we begin our story [PAUSE] which just might rekindle` → `clause`。`which` 引导定语从句，是分句边界。
- `that memory [PAUSE] of a boy` → `tight`。`of a boy` 是修饰语，和中心词 `memory` 不能断开。
- `He was twenty [PAUSE] and he was in the war` → `clause`。并列连词前。
- `Well [PAUSE] it was in somebody's house` → `drop`。填充词黏在主句上。
- `...a full sentence. [PAUSE] Then a new thought begins` → `clause`（默认），**不是** tight —— 句末不能用 tight。
- 若上一条你判断「缩到 0.2s 会明显损失力度」，才升为 `beat`。

## 输出格式

纯 JSON（不要 markdown 代码块、不要注释），写到指定路径：

```json
{
  "P001": {"kind": "clause", "why": "which 引导定语从句"},
  "P002": {"kind": "drop", "why": "填充词后紧接主句"}
}
```

`why` 用中文，不超过 20 字，必须写出你依据的是哪个词/哪个结构。

## 待标样本（40 条）

**P001**  call of a loon echoed across the lake. [PAUSE] Venus abided in the sky, calm and radiant,

**P002**  a stack of books sat by his side. [PAUSE] He rifled open a book, shown his flashlight

**P003**  realms. Athletes are running laps. Mountaineers scaling slopes. [PAUSE] Gardeners are planting seeds. Big brothers skipping stones,

**P004**  sprouting and budding in every patch of soil [PAUSE] and sliver of sunlight. Seagrass is covering saltwater

**P005**  verses, farmers picking berries, skiers carting carving hillsides, [PAUSE] leaders giving speeches, doctors hearing heartbeats, and kids

**P006**  sitting on Earth in the Milky Way galaxy, [PAUSE] in a community of galaxies that has the

**P007**  or scary or sad. My love, said Grandpa, [PAUSE] stuff that might happen in the future can't

**P008**  to the one that he or she loves. [PAUSE] Someone is daydreaming under the cover of clouds.

**P009**  a mountain. People are calculating equations, baking souffles, [PAUSE] and watching sunsets. are somersaulting and storytelling, dancing

**P010**  it faded to nothing, like an ephemeral pinstroke [PAUSE] disappearing as soon as imprinted. Zoe settled in

**P011**  call a paused and this single marvellous moment [PAUSE] was stretching on forever. A narrow wooden dock

**P012**  life growing all across this world of ours, [PAUSE] lush landscapes flourishing with roots and trunks, branches

**P013**  of black sand. Off the coast of Portugal, [PAUSE] waves rising as eyes, hills are rolling calmly

**P014**  behind, snug the dinosaur, bumping atop the steps. [PAUSE] So he slipped out the back door and

**P015**  passes, cooks stirring sauces, poets penning verses, farmers [PAUSE] picking berries, skiers carting carving hillsides, leaders giving

**P016**  dreams being dreamed, and lives being lived this [PAUSE] very instant. We can't be sure who or

**P017**  fleeting and silent. In this moment, Grandpa continued, [PAUSE] our planet is passing through a trail of

**P018**  see it. As we swing on this bench, [PAUSE] we're perched on a planet, rotating on its

**P019**  happening, events unfolding at every reach and depth [PAUSE] of this planet. All at once it is

**P020**  into bed and allowed her head to fall [PAUSE] into the pillow. Grandpa tucked her in with

**P021**  ones paired together. They arrived with different intensities, [PAUSE] some short and faint, others long and bright.

**P022**  rippling on water comets sailing around the sun. [PAUSE] She thought of her favorite place on the

**P023**  as if watching over the night. and then [PAUSE] last meteor soared above the horizon, a slow,

**P024**  the sky, fleeting and silent. In this moment, [PAUSE] Grandpa continued, our planet is passing through a

**P025**  is floating freely in zero gravity. Someone else [PAUSE] cannonballing off a diving board. Someone is peering

**P026**  seeing now, that twinkling glimmer in the sky, [PAUSE] left the star before you were born. Just

**P027**  is roaming tropical shallows, a colony of penguins [PAUSE] huddling on Antarctic ice floes, pride of lions

**P028**  learning the language. A singer humming a ballad. [PAUSE] A teacher is imparting knowledge. An artist revealing

**P029**  seeping into aquifers, and bubbling up from springs. [PAUSE] In this moment in time, there are millions

**P030**  to unfold in all its patience and beauty. [PAUSE] The lake rippling, the trees swaying, the sky

**P031**  universe. Her imagination floating between coins and fountains, [PAUSE] clouds and skies, Meteors over mountains wails under

**P032**  drawings on the wall. Green birds, blue bears, [PAUSE] and red fish. Cardboard models of the planets

**P033**  anticipation stirring in her chest. Another meteor appeared, [PAUSE] and then another, and then two tiny ones

**P034**  hearts that are beating, lungs breathing, minds musing. [PAUSE] Consider the kisses being kissed, dreams being dreamed,

**P035**  branches in a tranquil procession. Across the lake, [PAUSE] faint light shone from a scattering of cottages

**P036**  and fountains, clouds and skies, Meteors over mountains [PAUSE] wails under tides, Her breath eased to a

**P037**  Scientists researching microscopic realms. Athletes are running laps. [PAUSE] Mountaineers scaling slopes. Gardeners are planting seeds. Big

**P038**  stairs. Her blanket, draping behind, snug the dinosaur, [PAUSE] bumping atop the steps. So he slipped out

**P039**  Texas, longhorns are idling in pastures, some grazing, [PAUSE] some lazing, some sleeping in the hush of

**P040**  tides, Her breath eased to a tender rhythm, [PAUSE] Like a cascade of comfort washing over her.
