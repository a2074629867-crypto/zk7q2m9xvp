# 旁白停顿判档任务（马修规则 v2）

## 你要做什么

给下面 180 个句子里**每一个逗号**判一个档位：`inner` 还是 `bound`。

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

## 待判文本（180 句 / 275 个逗号）

**[N0001]** Three months ago, his grandmother died, and then they had moved to this house.

　　· 逗号1：`ago` ‖ `his`
　　· 逗号2：`died` ‖ `and`

**[N0003]** Though the old man lay upstairs, after a second stroke, and lingered, giving no trouble.

　　· 逗号1：`upstairs` ‖ `after`
　　· 逗号2：`stroke` ‖ `and`
　　· 逗号3：`lingered` ‖ `giving`

**[N0005]** his father said, nervously,

　　· 逗号1：`said` ‖ `nervously,`
　　· 逗号2：`nervously` ‖ ``

**[N0006]** And that was no more than the truth, though his father would not have believed it.

　　· 逗号1：`truth` ‖ `though`

**[N0007]** It will be very moving, Joseph Hooper had decided, with the three generations together and one upon his deathbed,

　　· 逗号1：`moving` ‖ `Joseph`
　　· 逗号2：`decided` ‖ `with`
　　· 逗号3：`deathbed` ‖ ``

**[N0009]** For, in middle age, he was acquiring a dynastic sense.

　　· 逗号1：`For` ‖ `in`
　　· 逗号2：`age` ‖ `he`

**[N0011]** The old man had breathed noisily, and dribbled a little, and never woken.

　　· 逗号1：`noisily` ‖ `and`
　　· 逗号2：`little` ‖ `and`

**[N0013]** Mr Hooper had said, and coughed,

　　· 逗号1：`said` ‖ `and`
　　· 逗号2：`coughed` ‖ ``

**[N0015]** His skin is already dead, he thought, it is old and dry.

　　· 逗号1：`dead` ‖ `he`
　　· 逗号2：`thought` ‖ `it`

**[N0016]** But he saw that the bones of the eye-sockets, and the nose and jaw, showed through it, and gleamed.

　　· 逗号1：`eye-sockets` ‖ `and`
　　· 逗号2：`jaw` ‖ `showed`
　　· 逗号3：`it` ‖ `and`

**[N0017]** Everything about him, from the stubble of hair down to the folded line of sheet, was bleached and grey-ish white.

　　· 逗号1：`him` ‖ `from`
　　· 逗号2：`sheet` ‖ `was`

**[N0018]** Edmund Hooper said,

　　· 逗号1：`said` ‖ ``

**[N0020]** Though I am only able to show respect now, he thought, to behave towards my father as I should, because he is dying,

　　· 逗号1：`now` ‖ `he`
　　· 逗号2：`thought` ‖ `to`
　　· 逗号3：`should` ‖ `because`
　　· 逗号4：`dying` ‖ ``

**[N0022]** Edmund Hooper, walking down the great staircase into the woodpannelled hall, thought nothing of his grandfather.

　　· 逗号1：`Hooper` ‖ `walking`
　　· 逗号2：`hall` ‖ `thought`

**[N0023]** But later, he remembered the moth-like whiteness of the very old skin.

　　· 逗号1：`later` ‖ `he`

**[N0024]** Now, they had moved, Joseph Hooper was master in his own house.

　　· 逗号1：`Now` ‖ `they`
　　· 逗号2：`moved` ‖ `Joseph`

**[N0026]** He looked away from his son’s gaze, irritated.

　　· 逗号1：`gaze` ‖ `irritated.`

**[N0027]** I do my best, he thought, it is not the easiest of tasks without a woman beside me.

　　· 逗号1：`best` ‖ `he`
　　· 逗号2：`thought` ‖ `it`

**[N0029]** Edmund Hooper thought, I don’t want anything to be done about it, nobody must come here,

　　· 逗号1：`thought` ‖ `I`
　　· 逗号2：`it` ‖ `nobody`
　　· 逗号3：`here` ‖ ``

**[N0031]** Joseph Hooper sighed, sitting at his desk, in the room facing the long lawn.

　　· 逗号1：`sighed` ‖ `sitting`
　　· 逗号2：`desk` ‖ `in`

**[N0032]** For the time being, the house was to be kept as it was, until he could decide which of the furniture to be rid of,

　　· 逗号1：`being` ‖ `the`
　　· 逗号2：`was` ‖ `until`
　　· 逗号3：`of` ‖ ``

**[N0034]** He moved his hands uneasily about over the papers on his desk, oppressed by them, uncertain where he should begin.

　　· 逗号1：`desk` ‖ `oppressed`
　　· 逗号2：`them` ‖ `uncertain`

**[N0036]** But his father’s affairs had been left in disarray, he was ashamed of the paraphernalia of death.

　　· 逗号1：`disarray` ‖ `he`

**[N0037]** M Joseph Hooper moved his hand towards the small, left-side drawer in the desk, underneath the drawer where sealing wax had always been kept.

　　· 逗号1：`small` ‖ `left-side`
　　· 逗号2：`desk` ‖ `underneath`

**[N0038]** But then, said,

　　· 逗号1：`then` ‖ `said,`
　　· 逗号2：`said` ‖ ``

**[N0039]** Hooper went out, wishing he had said nothing.

　　· 逗号1：`out` ‖ `wishing`

**[N0040]** He wanted nothing to be done, nobody should come here.

　　· 逗号1：`done` ‖ `nobody`

**[N0042]** He is like his mother, thought Mr Joseph Hooper.

　　· 逗号1：`mother` ‖ `thought`

**[N0043]** He has the same way of not bothering to explain, and of making secrets, the same hardness and cool way of looking.

　　· 逗号1：`explain` ‖ `and`
　　· 逗号2：`secrets` ‖ `the`

**[N0046]** When his son, who so resembled her, was away at school,

　　· 逗号1：`son` ‖ `who`
　　· 逗号2：`her` ‖ `was`
　　· 逗号3：`school` ‖ ``

**[N0049]** The house, which was called Warings, had been built by the boy’s great-grandfather, and so it was not very old.

　　· 逗号1：`house` ‖ `which`
　　· 逗号2：`Warings` ‖ `had`
　　· 逗号3：`great-grandfather` ‖ `and`

**[N0050]** In those days, there had been a large village, and the first Joseph Hooper had owned a good deal of land.

　　· 逗号1：`days` ‖ `there`
　　· 逗号2：`village` ‖ `and`

**[N0051]** Now, the village had shrunk, people had left for the towns and there had been few newcomers, few new buildings.

　　· 逗号1：`Now` ‖ `the`
　　· 逗号2：`shrunk` ‖ `people`
　　· 逗号3：`newcomers` ‖ `few`

**[N0053]** All the Hooper land had been sold off, piece by piece.

　　· 逗号1：`off` ‖ `piece`

**[N0054]** But there was still Warings, built on a slope leading out of the village, some distance from any other house.

　　· 逗号1：`Warings` ‖ `built`
　　· 逗号2：`village` ‖ `some`

**[N0055]** The first Joseph Hooper had been a banker, and rising in the world, when, at the age of thirty, he had built the house.

　　· 逗号1：`banker` ‖ `and`
　　· 逗号2：`world` ‖ `when,`
　　· 逗号3：`when` ‖ `at`
　　· 逗号4：`thirty` ‖ `he`

**[N0057]** And indeed, he had spent more on it that he could well afford.

　　· 逗号1：`indeed` ‖ `he`

**[N0058]** He hoped to grow into it, as a child grows into over-large shoes.

　　· 逗号1：`it` ‖ `as`

**[N0060]** He had brought the younger daughter of a minor baronet here, as his bride, and set about founding his family, consolidating a position,

　　· 逗号1：`here` ‖ `as`
　　· 逗号2：`bride` ‖ `and`
　　· 逗号3：`family` ‖ `consolidating`
　　· 逗号4：`position` ‖ ``

**[N0062]** He had succeeded with no margin, so that, bit by bit, the surrounding land which belonged to him had been sold.

　　· 逗号1：`margin` ‖ `so`
　　· 逗号2：`that` ‖ `bit`
　　· 逗号3：`bit` ‖ `the`

**[N0063]** the present Joseph Hooper had told his son, Edmund, taking him solemnly around.

　　· 逗号1：`son` ‖ `Edmund,`
　　· 逗号2：`Edmund` ‖ `taking`

**[N0065]** It was an ordinary house, he thought, an ugly house, nothing to boast of.

　　· 逗号1：`house` ‖ `he`
　　· 逗号2：`thought` ‖ `an`
　　· 逗号3：`house` ‖ `nothing`

**[N0066]** But the idea that it was his, the idea of a family history, pleased him.

　　· 逗号1：`his` ‖ `the`
　　· 逗号2：`history` ‖ `pleased`

**[N0067]** His father said,

　　· 逗号1：`said` ‖ ``

**[N0068]** Though he thought, what does it mean, it means so little, to himself.

　　· 逗号1：`thought` ‖ `what`
　　· 逗号2：`mean` ‖ `it`
　　· 逗号3：`little` ‖ `to`

**[N0069]** And he shrank from the expression in the boy’s eyes, from his knowingness.

　　· 逗号1：`eyes` ‖ `from`

**[N0072]** It was entirely graceless, rather tall and badly angled, built of dark red brick.

　　· 逗号1：`graceless` ‖ `rather`
　　· 逗号2：`angled` ‖ `built`

**[N0073]** At the front, and on both sides, there was the lawn, sloping downwards to a gravelled drive.

　　· 逗号1：`front` ‖ `and`
　　· 逗号2：`sides` ‖ `there`
　　· 逗号3：`lawn` ‖ `sloping`

**[N0074]** And then into the lane, and without any tree or flower-bed to relieve the bald greenness.

　　· 逗号1：`lane` ‖ `and`

**[N0075]** Up the drive, and at the back of the house, bunched between the yew trees, were the great bushes of rhododendron.

　　· 逗号1：`drive` ‖ `and`
　　· 逗号2：`house` ‖ `bunched`
　　· 逗号3：`trees` ‖ `were`

**[N0076]** The yew trees had stood here before the house, Warings, had been built around them, for the first Joseph Hooper had admired their solidity and denseness,

　　· 逗号1：`house` ‖ `Warings,`
　　· 逗号2：`Warings` ‖ `had`
　　· 逗号3：`them` ‖ `for`
　　· 逗号4：`denseness` ‖ ``

**[N0078]** He had planted the rhododendrons, too, not at all for their brief, dramatic show of colour in May and June, but for their dark green,

　　· 逗号1：`rhododendrons` ‖ `too,`
　　· 逗号2：`too` ‖ `not`
　　· 逗号3：`brief` ‖ `dramatic`
　　· 逗号4：`June` ‖ `but`
　　· 逗号5：`green` ‖ ``

**[N0080]** He liked their gathered shapes, seen from the end of the drive.

　　· 逗号1：`shapes` ‖ `seen`

**[N0081]** Inside the house, everything was predictable, the high-ceilinged rooms, with heavy, sashed windows,

　　· 逗号1：`house` ‖ `everything`
　　· 逗号2：`predictable` ‖ `the`
　　· 逗号3：`rooms` ‖ `with`
　　· 逗号4：`heavy` ‖ `sashed`
　　· 逗号5：`windows` ‖ ``

**[N0082]** the oak wall panelling and the oak doors, and the oak staircase, the massive furniture.

　　· 逗号1：`doors` ‖ `and`
　　· 逗号2：`staircase` ‖ `the`

**[N0084]** Joseph Hooper had spent that part of his childhood before school, and between terms, in this house, and he did not like it,

　　· 逗号1：`school` ‖ `and`
　　· 逗号2：`terms` ‖ `in`
　　· 逗号3：`house` ‖ `and`
　　· 逗号4：`it` ‖ ``

**[N0086]** Yet now, at the age of fifty-one, he admitted that he was a Hooper, his father’s son,

　　· 逗号1：`now` ‖ `at`
　　· 逗号2：`fifty-one` ‖ `he`
　　· 逗号3：`Hooper` ‖ `his`
　　· 逗号4：`son` ‖ ``

**[N0088]** He thought, it is a prepossessing house.

　　· 逗号1：`thought` ‖ `it`

**[N0089]** For he knew himself to be an ineffectual man, without any strength or imposing qualities, a man who was liked and humoured but little regarded,

　　· 逗号1：`man` ‖ `without`
　　· 逗号2：`qualities` ‖ `a`
　　· 逗号3：`regarded` ‖ ``

**[N0090]** a man who failed – but not dramatically, as one falling from a great height, who attracts attention.

　　· 逗号1：`dramatically` ‖ `as`
　　· 逗号2：`height` ‖ `who`

**[N0091]** He was a dull man, a man who got by.

　　· 逗号1：`man` ‖ `a`

**[N0092]** He thought, I know myself and am depressed by what I know.

　　· 逗号1：`thought` ‖ `I`

**[N0093]** But now, with his father gone, he could stand before this house, and have it lend him both importance and support, he could speak of

　　· 逗号1：`now` ‖ `with`
　　· 逗号2：`gone` ‖ `he`
　　· 逗号3：`house` ‖ `and`
　　· 逗号4：`support` ‖ `he`

**[N0094]** , it would make up for a good deal.

　　· 逗号1：`` ‖ `it`

**[N0096]** That, and a field beyond it, were all that was now left of the Hooper land.

　　· 逗号1：`That` ‖ `and`
　　· 逗号2：`it` ‖ `were`

**[N0097]** The boy’s room, high up at the back of the house, overlooked the copse.

　　· 逗号1：`room` ‖ `high`
　　· 逗号2：`house` ‖ `overlooked`

**[N0099]** His father had said,

　　· 逗号1：`said` ‖ ``

**[N0100]** But he had wanted this, a narrow room with a tall window.

　　· 逗号1：`this` ‖ `a`

**[N0101]** Above him, there were only the attics.

　　· 逗号1：`him` ‖ `there`

**[N0102]** When he woke, now, there was an enormous moon, so that at first, he thought it was already dawn, and that he had missed his chance.

　　· 逗号1：`woke` ‖ `now,`
　　· 逗号2：`now` ‖ `there`
　　· 逗号3：`moon` ‖ `so`
　　· 逗号4：`first` ‖ `he`
　　· 逗号5：`dawn` ‖ `and`

**[N0104]** There was a slight, persistent movement of wind through the yew tree branches, and the elms and oaks of the copse,

　　· 逗号1：`slight` ‖ `persistent`
　　· 逗号2：`branches` ‖ `and`
　　· 逗号3：`copse` ‖ ``

**[N0106]** The moonlight, penetrating a thin space between two trees, caught the stream that ran through its centre, so that, now and then, as the branches stirred,

　　· 逗号1：`moonlight` ‖ `penetrating`
　　· 逗号2：`trees` ‖ `caught`
　　· 逗号3：`centre` ‖ `so`
　　· 逗号4：`that` ‖ `now`
　　· 逗号5：`then` ‖ `as`
　　· 逗号6：`stirred` ‖ ``

**[N0110]** Outside on his landing, there was no moonlight, and he felt his way in the dark, first on the carpeted upper staircase, and then,

　　· 逗号1：`landing` ‖ `there`
　　· 逗号2：`moonlight` ‖ `and`
　　· 逗号3：`dark` ‖ `first`
　　· 逗号4：`staircase` ‖ `and`
　　· 逗号5：`then` ‖ ``

**[N0111]** for the last two flights, on the bare, polished oak.

　　· 逗号1：`flights` ‖ `on`
　　· 逗号2：`bare` ‖ `polished`

**[N0112]** He went forward quite deliberately, being sure of his way, and unafraid.

　　· 逗号1：`deliberately` ‖ `being`
　　· 逗号2：`way` ‖ `and`

**[N0116]** It is too dark, she said, and it smells unlived in, of old things, like a museum.

　　· 逗号1：`dark` ‖ `she`
　　· 逗号2：`said` ‖ `and`
　　· 逗号3：`in` ‖ `of`
　　· 逗号4：`things` ‖ `like`

**[N0117]** And she had gone about trying to let in light and fresh air, where she could.

　　· 逗号1：`air` ‖ `where`

**[N0120]** Hooper crossed the wide hall, and here too, because it was the front of the house, no moonlight came.

　　· 逗号1：`hall` ‖ `and`
　　· 逗号2：`too` ‖ `because`
　　· 逗号3：`house` ‖ `no`

**[N0121]** Behind him, the wood of the staircase had settled back upon itself, after he had trodden it.

　　· 逗号1：`him` ‖ `the`
　　· 逗号2：`itself` ‖ `after`

**[N0122]** At first, he could not decide which key it might be, there were three together in the left-hand drawer.

　　· 逗号1：`first` ‖ `he`
　　· 逗号2：`be` ‖ `there`

**[N0123]** But one was longer, with a smudge of red paint across the rim.

　　· 逗号1：`longer` ‖ `with`

**[N0125]** It was at the back of the house, facing the copse, so that when he pushed open the door, he saw it in full moonlight,

　　· 逗号1：`house` ‖ `facing`
　　· 逗号2：`copse` ‖ `so`
　　· 逗号3：`door` ‖ `he`
　　· 逗号4：`moonlight` ‖ ``

**[N0126]** almost as bright as day, when the lights always had to go on, because of the yew branches, overhanging the windows.

　　· 逗号1：`day` ‖ `when`
　　· 逗号2：`on` ‖ `because`
　　· 逗号3：`branches` ‖ `overhanging`

**[N0128]** It had been designed, by the first Joseph Hooper, as a library, and there were still the glass cases, reaching from floor to ceiling,

　　· 逗号1：`designed` ‖ `by`
　　· 逗号2：`Hooper` ‖ `as`
　　· 逗号3：`library` ‖ `and`
　　· 逗号4：`cases` ‖ `reaching`
　　· 逗号5：`ceiling` ‖ ``

**[N0129]** all around the room, filled with books.

　　· 逗号1：`room` ‖ `filled`

**[N0130]** But nobody ever read, here.

　　· 逗号1：`read` ‖ `here.`

**[N0132]** Edmund Hooper examined the titles of some of the books the day he was brought here to see his dying grandfather,

　　· 逗号1：`grandfather` ‖ ``

**[N0134]** There were bound volumes of the Banker’s Journal and the Stockbroker’s Gazette, and complete sets of the Victorian novelists, never opened.

　　· 逗号1：`Gazette` ‖ `and`
　　· 逗号2：`novelists` ‖ `never`

**[N0135]** It was his grandfather, recently dead, who had started to make use of the Red Room.

　　· 逗号1：`grandfather` ‖ `recently`
　　· 逗号2：`dead` ‖ `who`

**[N0137]** It was like the room of a museum, for here was no carpet on the polished oak boards,

　　· 逗号1：`museum` ‖ `for`
　　· 逗号2：`boards` ‖ ``

**[N0138]** and the display cases stood in two long rows, from one end to the other.

　　· 逗号1：`rows` ‖ `from`

**[N0139]** There were trays of insects, too, which you could pull out from recesses in the walls.

　　· 逗号1：`insects` ‖ `too,`
　　· 逗号2：`too` ‖ `which`

**[N0140]** Joseph Hooper had said, showing the boy round.

　　· 逗号1：`said` ‖ `showing`

**[N0141]** Though what use is it, he thought, what use, why should I not sell it?

　　· 逗号1：`it` ‖ `he`
　　· 逗号2：`thought` ‖ `what`
　　· 逗号3：`use` ‖ `why`

**[N0143]** He had been brought in here, afternoon upon afternoon, during the summers of his boyhood, led all about the room from cabinet to cabinet,

　　· 逗号1：`here` ‖ `afternoon`
　　· 逗号2：`afternoon` ‖ `during`
　　· 逗号3：`boyhood` ‖ `led`
　　· 逗号4：`cabinet` ‖ ``

**[N0144]** he was lectured and instructed, he had been forced to watch as the insects were removed from their poison-fume bottles with tweezers,

　　· 逗号1：`instructed` ‖ `he`
　　· 逗号2：`tweezers` ‖ ``

**[N0146]** his father had said,

　　· 逗号1：`said` ‖ ``

**[N0147]** He had not dared to rebel, he had gone back into the Red Room every holiday, feigning interest, acquiring knowledge, disguising his fear.

　　· 逗号1：`rebel` ‖ `he`
　　· 逗号2：`holiday` ‖ `feigning`
　　· 逗号3：`interest` ‖ `acquiring`
　　· 逗号4：`knowledge` ‖ `disguising`

**[N0148]** Until, at last, he had grown older and found excuses for spending all of his holidays away from the house.

　　· 逗号1：`Until` ‖ `at`
　　· 逗号2：`last` ‖ `he`

**[N0149]** his father had said, seeing it was.

　　· 逗号1：`said` ‖ `seeing`

**[N0154]** Edmund Hooper had gone about the Red Room, looking closely, saying nothing.

　　· 逗号1：`Room` ‖ `looking`
　　· 逗号2：`closely` ‖ `saying`

**[N0155]** Joseph Hooper said,

　　· 逗号1：`said` ‖ ``

**[N0156]** He walked to the window and looked out onto the copse, swept by the first heavy rain of the summer.

　　· 逗号1：`copse` ‖ `swept`

**[N0157]** He did not say whether the stiff moths, inside their glass cases, interested him or not.

　　· 逗号1：`moths` ‖ `inside`
　　· 逗号2：`cases` ‖ `interested`

**[N0159]** But he understood, looking at the boy, a little of how it had been with his own father,

　　· 逗号1：`understood` ‖ `looking`
　　· 逗号2：`boy` ‖ `a`
　　· 逗号3：`father` ‖ ``

**[N0161]** I am not a hard man, he thought, I have more to regret about my own son than he had about me.

　　· 逗号1：`man` ‖ `he`
　　· 逗号2：`thought` ‖ `I`

**[N0162]** For he knew that he had failed, from the very beginning, to ingratiate himself with Edmund.

　　· 逗号1：`failed` ‖ `from`
　　· 逗号2：`beginning` ‖ `to`

**[N0164]** At first, Hooper walked up and down the room softly, looking at all the moths, laid out on white card, and at the labels beneath them.

　　· 逗号1：`first` ‖ `Hooper`
　　· 逗号2：`softly` ‖ `looking`
　　· 逗号3：`moths` ‖ `laid`
　　· 逗号4：`card` ‖ `and`

**[N0165]** The names pleased him – Hawk Moths, Footmen Moths, Lutestring Moths.

　　· 逗号1：`Moths` ‖ `Footmen`
　　· 逗号2：`Moths` ‖ `Lutestring`

**[N0166]** He read some of them out to himself, in a low voice.

　　· 逗号1：`himself` ‖ `in`

**[N0167]** Moonlight came through the window, coldly, on to the glass.

　　· 逗号1：`window` ‖ `coldly,`
　　· 逗号2：`coldly` ‖ `on`

**[N0168]** Above the wooden panelling of the Red Room were the animals, the stag’s head with antlers branching out over the doorway,

　　· 逗号1：`animals` ‖ `the`
　　· 逗号2：`doorway` ‖ ``

**[N0169]** and the cases of grey fish, against their painted backgrounds of weed and water, the stuffed bodies of weasel, stoat, and fox,

　　· 逗号1：`fish` ‖ `against`
　　· 逗号2：`water` ‖ `the`
　　· 逗号3：`weasel` ‖ `stoat,`
　　· 逗号4：`stoat` ‖ `and`
　　· 逗号5：`fox` ‖ ``

**[N0171]** Because of the old man’s long last illness, and the neglect of the housekeeper, it was some time since they had been cleaned.

　　· 逗号1：`illness` ‖ `and`
　　· 逗号2：`housekeeper` ‖ `it`

**[N0172]** Mr Joseph Hooper had said that the animals should be sold, they were not a matter of family pride,

　　· 逗号1：`sold` ‖ `they`
　　· 逗号2：`pride` ‖ ``

**[N0173]** they had only been bought in a lot by the first Joseph Hooper, who wanted to equip his library in the manner of a sporting person.

　　· 逗号1：`Hooper` ‖ `who`

**[N0174]** Hooper stopped in front of a case at the far end of the room, beside the uncurtained window.

　　· 逗号1：`room` ‖ `beside`

**[N0175]** He looked down at the flat, fragile shapes.

　　· 逗号1：`flat` ‖ `fragile`

**[N0176]** He was fascinated by them, excited.

　　· 逗号1：`them` ‖ `excited.`

**[N0179]** A puff of old, stale-smelling air came into his face.

　　· 逗号1：`old` ‖ `stale-smelling`

**[N0181]** – though he could only just make out the writing on the card, the ink had faded to a dark yellow in the sun.

　　· 逗号1：`card` ‖ `the`

**[N0182]** He stretched out his hand, put his finger under the head of the pin and slid it up, out of the thick, striped body.

　　· 逗号1：`hand` ‖ `put`
　　· 逗号2：`up` ‖ `out`
　　· 逗号3：`thick` ‖ `striped`

**[N0183]** At once, the whole moth, already years dead, disintegrated, collapsing into a soft, formless heap of dark dust.

　　· 逗号1：`once` ‖ `the`
　　· 逗号2：`moth` ‖ `already`
　　· 逗号3：`dead` ‖ `disintegrated,`
　　· 逗号4：`disintegrated` ‖ `collapsing`
　　· 逗号5：`soft` ‖ `formless`
