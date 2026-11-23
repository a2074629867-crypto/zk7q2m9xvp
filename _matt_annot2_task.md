# 旁白停顿句法标注（马修母带 · 第二轮 · 盲标）

你是三方交叉验证中的一票。**独立判断。不要猜"标准答案"，也不要猜停顿有多长。**

## 素材

《Wonder》有声书旁白（男声，睡前故事语调，107wpm）。每一条是一段连续文本，
中间 `[PAUSE]` 标出一处**真实存在的停顿**。判断这处停顿的**句法性质**。

> **不要估算时长。** 我们刻意不给时长——给了就会锚定。你只判结构，时长我们事后统计。

## 只有四档

| kind | 判据 |
|---|---|
| `inner` | **停顿切开的是同一个成分的内部。** 后半是前半中某个词的**修饰语/补足语**。<br>典型：中心词 ← 介词短语（`a memory \| of a boy`）、名词 ← 分词（`penguins \| huddling`）、动词 ← 介词短语（`fall \| into the pillow`）、主语 ← 谓语（`the moment \| was stretching`）、限定词 ← 名词（`this \| very instant`）<br>**测试：问"后半在修饰前半的哪个词？"——能明确答出那个词 → inner** |
| `bound` | **停顿切开的是两个不同成分，但这句话还没说完。**<br>典型：并列项之间（`bears \| and red fish`）、同位语引入（`intensities \| some short bursts`）、插入语闭合后回主句（`he said \| Grandpa \| ...`）、总述后接列举、前置状语后接主句<br>**测试：问"后半在修饰前半的哪个词？"——答不出具体词，它是并列/同位/新成分 → bound** |
| `clause` | **一句话说完了。** 停顿前后是两个可以各自独立的句子/分句。<br>这是句末的默认档。`...echoed across the lake. \| Venus abided in the sky` |
| `para` | **话题/场景/视角切换。** 不只是句子结束，是"换了一段"。<br>判据：前一句和后一句讲的**不是同一件事**（时间跳、地点跳、叙述→内心独白） |

**已取消的两档，不要使用：** `drop`（"不停也行"）和 `beat`（"情绪落点"）。
上一轮实测证明马修在每个标点位置都停，且旁白没有情绪落点。判成这两档会直接算错。

## 判定顺序（必须按顺序，每条问一遍）

1. **后半能独立成句吗？** 不能，且它在修饰前半某个词 → `inner`
2. 不能独立成句，但它不修饰前半任何词（是并列/同位/新成分） → `bound`
3. 能独立成句，且和前半讲同一件事 → `clause`
4. 能独立成句，且换了话题/场景/视角 → `para`

## 反例（上一轮标错的）

- `the depth [PAUSE] of this planet` → `inner`。`of this planet` 修饰 `depth`。
- `pinstroke [PAUSE] disappearing into the folds` → `inner`。分词修饰 `pinstroke`。
- `the intensities [PAUSE] some short bursts of light` → `bound`。同位语，不修饰 `intensities` 这个词本身。
- `He fell into the pillow [PAUSE] and the dinosaur bumped` → `bound`。并列项之间。
- `...a full sentence. [PAUSE] Then a new thought` → `clause`，**不是** `inner`——句末不能用 inner。
- `call of a loon echoed across the lake. [PAUSE] Venus abided in the sky` → `clause`。
- 若前后讲的是不同场景/时间 → 才升 `para`。

## 输出格式

纯 JSON（不要代码块围栏、不要注释），写到指定路径：

```
{
  "Q001": {"kind": "inner", "why": "of a boy 修饰 memory"},
  "Q002": {"kind": "bound", "why": "并列宾语之间"}
}
```

`why` 用中文，≤20 字，**必须点名你依据的那个词或那个结构**。

## 待标样本（60 条）

**Q001**  just like us since at any given moment [PAUSE] the present moment is all we ever have

**Q002**  Zoe closed her eyes, and began drifting off [PAUSE] to an ocean of gratitude and wonderment, rolling

**Q003**  there lives an adorable 187 -year -old tortoise [PAUSE] named Jonathan, Even oldest known living land animal

**Q004**  of the waves curling up on the rocks, [PAUSE] the drift of the breeze coasting through the

**Q005**  the corner, organized from big at the bottom [PAUSE] to tiny at the top. Stock of prized

**Q006**  lights. They suspended above, so large and luminous [PAUSE] that Zoe almost felt as if she could

**Q007**  cosmos. Then, as Grandpa looked into the eyepiece, [PAUSE] a smile uncoiled upon his face. like the

**Q008**  some short and faint, others long and bright. [PAUSE] They voyaged in the same direction, crossing from

**Q009**  words assembled into endless variations of stories, expressions, [PAUSE] answers, and questions. Such an abundance of souls

**Q010**  dreams being dreamed, and lives being lived this [PAUSE] very instant. We can't be sure who or

**Q011**  to doze off to sleep. Her eyelids heavy, [PAUSE] her breath soft deep. Grandpa guided her back

**Q012**  happen, things that are crummy or bad or [PAUSE] scary or sad. My love, said Grandpa, stuff

**Q013**  which just might rekindle that sense of wonder. [PAUSE] It was the rattle of an antique telescope

**Q014**  was sleeping soundly. Then Zoe heard it again, [PAUSE] had curious rattling, and it sounded like it

**Q015**  seeing now, that twinkling glimmer in the sky, [PAUSE] left the star before you were born. Just

**Q016**  grandpa sat in silence for a few minutes [PAUSE] the universe to unfold in all its patience

**Q017**  the sky, fleeting and silent. In this moment, [PAUSE] Grandpa continued, our planet is passing through a

**Q018**  players are throwing passes, cooks stirring sauces, poets [PAUSE] penning verses, farmers picking berries, skiers carting carving

**Q019**  pushed his heel down against the floor and [PAUSE] gave the bench a nice heave. He and

**Q020**  a hand of anticipation stirring in her chest. [PAUSE] Another meteor appeared, and then another, and then

**Q021**  grabbed a hold of her favorite stuffed animal, [PAUSE] snug the dinosaur. It was baby blue with

**Q022**  heights, some higher in the sky. some lower [PAUSE] toward the horizon. Zoe and Grandpa watched as

**Q023**  trail of debris left behind by a comet [PAUSE] long ago, and as those pieces of icy

**Q024**  how far that starlight traveled just for you [PAUSE] to see it. As we swing on this

**Q025**  at once it is both autumn and spring, [PAUSE] day and night, dawn and dusk. Clouds are

**Q026**  into bed and allowed her head to fall [PAUSE] into the pillow. Grandpa tucked her in with

**Q027**  are rolling calmly toward the shore. In Venezuela, [PAUSE] a gentle flow of water is cascading down

**Q028**  up from springs. In this moment in time, [PAUSE] there are millions of species sharing this world

**Q029**  Grandpa, stuff that might happen in the future [PAUSE] can't happen now because we're in the present

**Q030**  faces, all of us sharing a common journey, [PAUSE] each of us wishing and wondering, breathing this

**Q031**  green spikes, wide eyes, and a friendly smile. [PAUSE] She snuck into the hall and patted down

**Q032**  circular lake. Starlight glimmered on the rippling water, [PAUSE] and delicate waves lapped up against the rocky

**Q033**  the telescope to re -inspect the cosmos. Then, [PAUSE] as Grandpa looked into the eyepiece, a smile

**Q034**  Clouds are converging and clearing, storms looming and [PAUSE] heating and cooling, tides rising and falling. Rainbows

**Q035**  patted down the stairs. Her blanket, draping behind, [PAUSE] snug the dinosaur, bumping atop the steps. So

**Q036**  board. Someone is peering down at a caterpillar, [PAUSE] someone else staring up at a mountain. People

**Q037**  are idling in pastures, some grazing, some lazing, [PAUSE] some sleeping in the hush of night. Just

**Q038**  and spring, day and night, dawn and dusk. [PAUSE] Clouds are converging and clearing, storms looming and

**Q039**  call a paused and this single marvellous moment [PAUSE] was stretching on forever. A narrow wooden dock

**Q040**  endless variations of stories, expressions, answers, and questions. [PAUSE] Such an abundance of souls roam this earth,

**Q041**  clouds, raining down on the hills and fields, [PAUSE] down from leafy trees, trickling into streams, flowing

**Q042**  began drifting off to an ocean of gratitude [PAUSE] and wonderment, rolling and flowing in her heart.

**Q043**  the moment. Starlight glowed in through the window [PAUSE] the soothing sounds of breeze and waves whispered

**Q044**  we looking for? Zoe asked. Venus, Grandpa replied, [PAUSE] pointing Skyward to a bright object, and a

**Q045**  of the solar system. And that entire system [PAUSE] is itself orbiting a galaxy at a speed

**Q046**  across the sky like a canopy of lights. [PAUSE] They suspended above, so large and luminous that

**Q047**  snowfall. They are everywhere our telescopes can see, [PAUSE] strewn upon space and arranged into giant groupings

**Q048**  lullabies to newborn sons and daughters. A student [PAUSE] is learning the language. A singer humming a

**Q049**  a line of white sailing amid the stars. [PAUSE] But just like that, it faded to nothing,

**Q050**  dinosaur. It was baby blue with green spikes, [PAUSE] wide eyes, and a friendly smile. She snuck

**Q051**  back door and onto the cozy wooden deck. [PAUSE] She wasn't sure how, but the breeze felt

**Q052**  a portion of page, discovered something of note, [PAUSE] and returned to the telescope to re -inspect

**Q053**  drawings on the wall. Green birds, blue bears, [PAUSE] and red fish. Cardboard models of the planets

**Q054**  and wonderment, rolling and flowing in her heart. [PAUSE] She thought of porch lights rippling on water

**Q055**  daisies swaying on roadsides, aspens rising from valleys. [PAUSE] As we sit our beloved lake, human beings

**Q056**  floating between coins and fountains, clouds and skies, [PAUSE] Meteors over mountains wails under tides, Her breath

**Q057**  daydreaming under the cover of clouds. Someone else [PAUSE] reveling in the splendor of sunlight. Someone is

**Q058**  to sleep. Her eyelids heavy, her breath soft [PAUSE] deep. Grandpa guided her back inside, up the

**Q059**  hung from the ceiling, from Mercury to Neptune, [PAUSE] and even Pluto for good measure. She knew

**Q060**  with us. harmony of living things dwelling at [PAUSE] every mountain peak and ocean floor. Somewhere out
