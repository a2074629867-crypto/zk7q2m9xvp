# 旁白停顿判档任务（马修规则 v2）

## 你要做什么

给下面 203 个句子里**每一个逗号**判一个档位：`inner` 还是 `bound`。

**句末句号不用判**，已默认 `clause`。

## 背景（为什么只判逗号）

这是《Wonder》有声书旁白母带的实测结论：
- 218 个逗号位置，96% 都有 ≥0.12s 的停顿，中位 1.16s
- 143 个句号位置，99% 都有停顿，中位 1.58s
- 2149 个非标点词间位置，只有 1.5% 有 ≥0.3s 停顿（换气）

⇒ **停顿位置完全由标点决定，不存在"该不该停"的问题。**
你只需要回答：这个逗号切开的，是**一个成分的内部**，还是**两个成分之间**。

## 两个档位

| tier | 判据 |
|---|---|
| `inner` | 逗号切开的**是同一个成分的内部**。后半是前半中某个词的修饰语/补足语。<br>典型：中心词←介词短语（`a memory, of a boy` 不是这种，见下）<br>真正典型：名词←分词（`penguins, huddling together`）、动词←介词短语（`fall, into the pillow`）、主语←谓语（`the moment, was stretching`）、限定词←名词（`this, very instant`）、并列短语内部（`from big, to tiny`、`crummy or bad, or scary`）<br>**测试：问"后半在修饰前半的哪个词？"——能明确点名 → inner** |
| `bound` | 逗号切开的是**两个不同成分**。后半不修饰前半任何词。<br>典型：并列项之间（`Green birds, blue bears, and red fish`）、同位语引入（`her favorite animal, Snug the dinosaur`）、插入语闭合后回主句（`In this moment, Grandpa continued, our planet...`）、前置状语后接主句（`In Venezuela, a gentle flow...`）、独立主格另起（`Her eyelids heavy, her breath soft`）、逗号分隔的分词状语（`sat in silence, letting the universe unfold`）<br>**测试：问"后半在修饰前半的哪个词？"——答不出，它是并列/同位/新成分 → bound** |

**没有第三档。** 不存在 `drop`（不停）或 `beat`（情绪落点）：
母带实测证明马修在每个逗号都停，且旁白没有情绪落点。判成这两种会直接算错。

## 判定顺序（每条逗号按顺序问）

1. 后半能独立成一个成分吗？不能，且它在修饰前半某个词 → `inner`
2. 能独立成成分，或它不修饰前半任何词（并列/同位/新成分） → `bound`

## 反例（最容易标错的三类）

- `the depth, of this planet` → `inner`。`of this planet` 修饰 `depth`。
- `the intensities, some short bursts of light` → `bound`。同位语，不修饰 `intensities` 这个词。
- `poets, penning verses` → `inner`。分词 `penning` 修饰 `poets`（独立主格）。
- `poets penning verses, farmers picking berries` → `bound`。两个独立主格并列。
- `He fell into the pillow, and the dinosaur bumped` → `bound`。并列分句。
- `sat in silence for a few minutes, letting the universe unfold` → `bound`。逗号分隔的分词状语，是新成分。
- `an adorable tortoise, named Jonathan` → `inner`。`named Jonathan` 是后置定语。

## 输出格式

纯 JSON（不要代码块围栏、不要注释），写到指定路径。键是句子 id，值是逗号序号 → 档位：

```
{
  "000": {"1": {"tier": "bound", "why": "which 引导定语从句"}},
  "005": {"1": {"tier": "inner", "why": "from big 与 to tiny 同属 from...to"}}
}
```

`why` 用中文，≤15 字，**必须点名具体词或结构**。
只输出骨架里出现的句子 id 和逗号序号，不要多也不要少。

## 待判文本（203 句 / 128 个逗号）

**[000]** as we begin our story, which just might rekindle that sense of was the rattle of an antique telescope that caught her attention on that quiet autumn night.

　　· 逗号1：`story` ‖ `which`

**[004]** Starlight cast a soft glow across the room, giving faint detail to the shapes of a comforting place.

　　· 逗号1：`room` ‖ `giving`

**[005]** A troop of stuffed animals piled in the corner, organized from big at the bottom to tiny at the top.

　　· 逗号1：`corner` ‖ `organized`

**[007]** Dinosaur figurines picture books, and a paper mache giraffe.

　　· 逗号1：`books` ‖ `and`

**[009]** Green birds, blue bears, and red fish.

　　· 逗号1：`birds` ‖ `blue`
　　· 逗号2：`bears` ‖ `and`

**[011]** From Mercury to Neptune, and even Pluto for good measure.

　　· 逗号1：`Neptune` ‖ `and`

**[012]** She knew they weren't to scale, but Such were the limits of the seven year old bedroom.

　　· 逗号1：`scale` ‖ `but`

**[017]** So she wrapped herself in a fuzzy blanket, and grabbed a hold of her favorite stuffed animal, Snug the dinosaur.

　　· 逗号1：`blanket` ‖ `and`
　　· 逗号2：`animal` ‖ `Snug`

**[018]** It was baby blue with green spikes, wide eyes, and a friendly smile.

　　· 逗号1：`spikes` ‖ `wide`
　　· 逗号2：`eyes` ‖ `and`

**[019]** She snuck into the hall and patted down the stairs, her blanket draping behind, snug the dinosaur bumping atop the steps.

　　· 逗号1：`stairs` ‖ `her`
　　· 逗号2：`behind` ‖ `snug`

**[021]** She wasn't sure how, But the breeze felt warm and cool all at the same time.

　　· 逗号1：`how` ‖ `But`

**[022]** A field of brilliant stars swept across the sky, like a canopy of lights.

　　· 逗号1：`sky` ‖ `like`

**[023]** They suspended above, so large and luminous that Zoe almost felt as if she could reach out and touch them.

　　· 逗号1：`above` ‖ `so`

**[029]** Across the lake, faint light shone from the scattering of cottages nestled along the shoreline, each sending a long reflection quivering upon the surface of the water.

　　· 逗号1：`lake` ‖ `faint`
　　· 逗号2：`shoreline` ‖ `each`

**[030]** A gentle gust of wind picked up And Zoe was enchanted by the collective rustling of a billion leaves, like a beautiful rousing whisper.

　　· 逗号1：`leaves` ‖ `like`

**[031]** And as the wind subsided, the leaves settled to stillness in the trees and on the ground, like an orchestral harmony fading to silence.

　　· 逗号1：`subsided` ‖ `the`
　　· 逗号2：`ground` ‖ `like`

**[033]** the drift of the breeze coasting through the trees, and the occasional call of a loon echoing across the lake.

　　· 逗号1：`trees` ‖ `and`

**[034]** It was so quiet, so peaceful.

　　· 逗号1：`quiet` ‖ `so`

**[035]** It felt as if time had paused, and this single marvelous moment was stretching on forever.

　　· 逗号1：`paused` ‖ `and`

**[036]** A narrow wooden dock extended into the lake, and in the darkness It appeared to hover a few feet above the water.

　　· 逗号1：`lake` ‖ `and`

**[037]** Standing at the end of the dock, peering into an eye piece of an antique telescope was Grandpa.

　　· 逗号1：`dock` ‖ `peering`

**[038]** A tussle of grayish white hair banded atop his head, reading glasses enfolded in his pocket, and a stack of books sat by his side.

　　· 逗号1：`head` ‖ `reading`
　　· 逗号2：`pocket` ‖ `and`

**[040]** shone his flashlight on a portion of page, discovered something of note, and returned to the telescope to reinspect the cosmos.

　　· 逗号1：`page` ‖ `discovered`
　　· 逗号2：`note` ‖ `and`

**[041]** Then, as Grandpa looked into the eye piece, a smile uncoiled upon his face, like the grin of Galileo himself.

　　· 逗号1：`Then` ‖ `as`
　　· 逗号2：`piece` ‖ `a`
　　· 逗号3：`face` ‖ `like`

**[044]** She reached her leg down and prodded the floor, easing the bench into motion.

　　· 逗号1：`floor` ‖ `easing`

**[048]** Grandpa pushed his heel down against the floor, and gave the bench a nice heave.

　　· 逗号1：`floor` ‖ `and`

**[049]** He and Zoe leaned back together, rocking back and forth, gazing up at the heavens.

　　· 逗号1：`together` ‖ `rocking`
　　· 逗号2：`forth` ‖ `gazing`

**[050]** As As their eyes wandered the constellations, Zoe explained that sometimes her mind would start racing and wouldn't stop.

　　· 逗号1：`constellations` ‖ `Zoe`

**[055]** But just like that it faded to nothing, like an ephemeral pen stroke, disappearing as soon as imprinted.

　　· 逗号1：`nothing` ‖ `like`
　　· 逗号2：`stroke` ‖ `disappearing`

**[056]** Zoe settled in under the blanket, and of anticipation stirring in her chest.

　　· 逗号1：`blanket` ‖ `and`

**[059]** They voyaged in the same direction, crossing from upper right to lower left.

　　· 逗号1：`direction` ‖ `crossing`

**[061]** Some higher in the sky, some lower toward the horizon.

　　· 逗号1：`sky` ‖ `some`

**[062]** Zoe and Grandpa watched as the spectacle ensued, delighted by this rare display of atmospheric fireworks.

　　· 逗号1：`ensued` ‖ `delighted`

**[063]** Sometimes a few moments of idleness would pass, and then a series of two or three meteors would appear, a flurry of fragments soaring across the sky, fleeting and silent.

　　· 逗号1：`pass` ‖ `and`
　　· 逗号2：`appear` ‖ `a`
　　· 逗号3：`sky` ‖ `fleeting`

**[064]** The greatest mountain in the solar system rises from the surface of Mars, peaking sixteen miles high.

　　· 逗号1：`Mars` ‖ `peaking`

**[066]** millions of comets roam the far reach of the solar system, leaving trails of icy dust on their enduring journeys.

　　· 逗号1：`system` ‖ `leaving`

**[067]** In this moment, the light from the bright star just overhead, called Sirius, is reaching Earth after traveling at one hundred and eighty-six thousand miles per second across eight light years of space.

　　· 逗号1：`moment` ‖ `the`
　　· 逗号2：`overhead` ‖ `called`
　　· 逗号3：`Sirius` ‖ `is`

**[068]** So the light you're seeing now, that twinkling glimmer in the sky, left the star before you were born.

　　· 逗号1：`now` ‖ `that`
　　· 逗号2：`sky` ‖ `left`

**[070]** As we swing on this bench, we're perched on a planet, rotating on its axis, while orbiting the star at the center of the solar system.

　　· 逗号1：`bench` ‖ `we're`
　　· 逗号2：`planet` ‖ `rotating`
　　· 逗号3：`axis` ‖ `while`

**[072]** So in a sense, right here, right now, we're galactic travelers on this vessel, we call Earth.

　　· 逗号1：`sense` ‖ `right`
　　· 逗号2：`here` ‖ `right`
　　· 逗号3：`now` ‖ `we're`
　　· 逗号4：`vessel` ‖ `we`

**[077]** They are everywhere our telescopes can see, strewn across space and arranged into giant groupings of galaxies.

　　· 逗号1：`see` ‖ `strewn`

**[078]** So in this moment, You are sitting on Earth in the Milky Way galaxy in a community of galaxies that has the lovely name of Lanichaea.

　　· 逗号1：`moment` ‖ `You`

**[079]** So as we relax on this November night, a beautiful balance of things are happening.

　　· 逗号1：`night` ‖ `a`

**[081]** All at once it is both autumn and and spring, day and night, dawn and dusk.

　　· 逗号1：`spring` ‖ `day`
　　· 逗号2：`night` ‖ `dawn`

**[088]** In New Zealand, misty clouds are gathering over beaches of black sand.

　　· 逗号1：`Zealand` ‖ `misty`

**[089]** Off the coast of Portugal, waves rising as high as hills are rolling calmly toward the shore.

　　· 逗号1：`Portugal` ‖ `waves`

**[090]** In Venezuela, A gentle flow of water is cascading down a breathtaking waterfall called Angel Falls, the highest in the world.

　　· 逗号1：`Venezuela` ‖ `A`
　　· 逗号2：`Falls` ‖ `the`

**[091]** That's happening right now, as we sit here.

　　· 逗号1：`now` ‖ `as`

**[092]** Everywhere on this earth, water is freezing into ice, melting into liquid.

　　· 逗号1：`earth` ‖ `water`
　　· 逗号2：`ice` ‖ `melting`

**[101]** Flowing down rivers, seeping into aquifers, and bubbling up from springs.

　　· 逗号1：`rivers` ‖ `seeping`
　　· 逗号2：`aquifers` ‖ `and`

**[102]** In this moment in time, there are millions of species sharing this world with us.

　　· 逗号1：`time` ‖ `there`

**[110]** In the waters off the Western Cape Humpback whales are wandering in murky serenity, sweeping and rolling, wise and graceful.

　　· 逗号1：`serenity` ‖ `sweeping`
　　· 逗号2：`rolling` ‖ `wise`

**[111]** On the open plains of Texas, longhorns are idling in pastures, some grazing Some lazing, some sleeping in the hush at night.

　　· 逗号1：`Texas` ‖ `longhorns`
　　· 逗号2：`pastures` ‖ `some`
　　· 逗号3：`lazing` ‖ `some`

**[112]** Just across the lake, a raft of loons are resting on the water.

　　· 逗号1：`lake` ‖ `a`

**[115]** There lives an adorable one hundred and eighty-seven year old tortoise named Jonathan, the oldest known living land animal in the world.

　　· 逗号1：`Jonathan` ‖ `the`

**[116]** And at this moment he's probably lumbering across a grassy field, his eying wisely, his head poking down from time to time.

　　· 逗号1：`field` ‖ `his`
　　· 逗号2：`wisely` ‖ `his`

**[122]** Vines are climbing up fences, ferns shading in forests, Daisies swaying on roadsides, Aspens rising from valleys.

　　· 逗号1：`fences` ‖ `ferns`
　　· 逗号2：`forests` ‖ `Daisies`
　　· 逗号3：`roadsides` ‖ `Aspens`

**[148]** At this very second, An adventurer is arriving home after a long journey with heroic tales to recount to the one that he or she loves.

　　· 逗号1：`second` ‖ `An`

**[155]** People are calculating equations, baking souffles, and watching sunsets.

　　· 逗号1：`equations` ‖ `baking`
　　· 逗号2：`souffles` ‖ `and`

**[160]** At this precise second, someone out there is seeing the shapes of animals in clouds.

　　· 逗号1：`second` ‖ `someone`

**[164]** Millions of words assembled into endless variations of stories, expressions, answers, and questions.

　　· 逗号1：`stories` ‖ `expressions,`
　　· 逗号2：`expressions` ‖ `answers,`
　　· 逗号3：`answers` ‖ `and`

**[165]** Such an abundance of souls roam this earth, a boundless array of human minds and faces, yet all of us sharing a common journey.

　　· 逗号1：`earth` ‖ `a`
　　· 逗号2：`faces` ‖ `yet`

**[166]** Each of us wishing and wandering, breathing this air, and seeing this sky.

　　· 逗号1：`wandering` ‖ `breathing`
　　· 逗号2：`air` ‖ `and`

**[167]** Just imagine the billions of hearts that are beating, lungs breathing, minds musing.

　　· 逗号1：`beating` ‖ `lungs`
　　· 逗号2：`breathing` ‖ `minds`

**[168]** Consider the kisses being kissed, dreams being dreamed, and lives being lived.

　　· 逗号1：`kissed` ‖ `dreams`
　　· 逗号2：`dreamed` ‖ `and`

**[171]** We are certain that at this moment another human being is gazing up at the sky, mesmerized, just like us.

　　· 逗号1：`sky` ‖ `mesmerized,`
　　· 逗号2：`mesmerized` ‖ `just`

**[172]** And since at any given moment, the present moment is all we ever have.

　　· 逗号1：`moment` ‖ `the`

**[173]** In this instant, in this magnificent moment.

　　· 逗号1：`instant` ‖ `in`

**[175]** And with that, Zoe and Grandpa sat in silence for a few minutes, allowing the universe to unfold in all its patience and beauty.

　　· 逗号1：`that` ‖ `Zoe`
　　· 逗号2：`minutes` ‖ `allowing`

**[176]** The lake ribling, the trees swaying, the sky expanding, the stars shimmering.

　　· 逗号1：`ribling` ‖ `the`
　　· 逗号2：`swaying` ‖ `the`
　　· 逗号3：`expanding` ‖ `the`

**[178]** The breeze coasted through the trees, and the call of a loon echoed across the lake.

　　· 逗号1：`trees` ‖ `and`

**[179]** Venus abided in the sky, calm and radiant, as if watching over the night.

　　· 逗号1：`sky` ‖ `calm`
　　· 逗号2：`radiant` ‖ `as`

**[181]** A slow, purposeful beam of light streaking splendidly like the final note in a majestic symphony.

　　· 逗号1：`slow` ‖ `purposeful`

**[182]** And young Zoe, inspired and exhausted, was ready to doze off to sleep.

　　· 逗号1：`Zoe` ‖ `inspired`
　　· 逗号2：`exhausted` ‖ `was`

**[183]** Her eyelids heavy, her breath soft and deep.

　　· 逗号1：`heavy` ‖ `her`

**[191]** She thought warmly of her dear grandpa, and all of his magical stories about the universe, her imagination floating between coins and fountains, clouds and skies, meteors over mountains, and whales under tides.

　　· 逗号1：`grandpa` ‖ `and`
　　· 逗号2：`universe` ‖ `her`
　　· 逗号3：`fountains` ‖ `clouds`
　　· 逗号4：`skies` ‖ `meteors`
　　· 逗号5：`mountains` ‖ `and`

**[196]** She delighted in the softness of her bed, and the quiet stillness of the moment.

　　· 逗号1：`bed` ‖ `and`

**[200]** Breathing slowly, peacefully, enwrapped in the warmth and safety of her bed.

　　· 逗号1：`slowly` ‖ `peacefully,`
　　· 逗号2：`peacefully` ‖ `enwrapped`
