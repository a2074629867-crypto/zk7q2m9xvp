# 英语句重音标注任务：句内焦点词

## 背景
这是一本英文小说有声书的旁白。我们要研究一个问题：**朗读时，句子里哪个词会读得最重（音高最高/最突出）？**

你的任务是**只根据文字**判断：这句话里，哪个词是「信息焦点」——说话人想让听者特别注意的那个词。

## 判定标准（按顺序问）

1. **对比焦点**：句子里有没有一个词是在和别的东西对比？（`It was the RATTLE of an antique telescope` — 不是望远镜本身，是它发出的咔嗒声）
2. **新信息**：这句话在告诉读者什么新东西？那个新东西的核心名词/动词。
3. **强调修饰**：有没有程度副词/形容词承载情绪重量？（`some of her FINEST drawings`）
4. **句末信息焦点**：英语习惯把新信息放句末。若前三条都没有明显答案，选句末的实词（不是介词/冠词）。

## 硬性规则

- **只能选一个词**，必须是这句话里**逐字出现**的词（含标点的要带上标点，如 `night.`）。
- **不要选功能词**（the / a / of / and / to / was / her / on），除非有特殊理由。
- **不要看音频**。这个任务只有文字。
- **独立判断**。不要读任何已有的标注文件。

## 输出格式

纯 JSON 写到 `G:/_setup/_matt_focus_hy4.json`：
```json
{
  "F01": {"focus": "wonder.", "why": "句末新信息，全段主题词"},
  "F02": {"focus": "rattle", "why": "对比焦点：不是望远镜，是它发出的声音"}
}
```
`focus` 必须是该句 `words` 数组里的某一项原文。40 个键 F01~F40 全都要有。

## 待标句子

**[F01]** Zoe sat up in bed and looked around her room.

**[F02]** Starlight cast a soft glow across the room, giving faint detail to the shapes of a comforting place.

**[F03]** Purple thumbtacks held some of her finest drawings on the wall.

**[F04]** Green birds, blue bears, and red fish.

**[F05]** She knew they weren't to scale, but such were the limits of a seven -year -old's bedroom.

**[F06]** In the bed next to Zoe's, her big sister Andrea had dozed off and was sleeping soundly.

**[F07]** Then Zoe heard it again, had curious rattling, and it sounded like it was coming from outside.

**[F08]** It was baby blue with green spikes, wide eyes, and a friendly smile.

**[F09]** So he slipped out the back door and onto the cozy wooden deck.

**[F10]** She wasn't sure how, but the breeze felt warm and cool all at the same time.

**[F11]** The field of brilliant stars swept across the sky like a canopy of lights.

**[F12]** She stared out across the small circular lake.

**[F13]** Standing at the end of the dock, peering into an eyepiece of an antique telescope, was Grandpa.

**[F14]** Then, as Grandpa looked into the eyepiece, a smile uncoiled upon his face.

**[F15]** like the grin of Galileo himself.

**[F16]** As their eyes wandered the constellations, so explained that sometimes her mind would start racing and wouldn't stop.

**[F17]** She would worry about stuff that might happen, things that are crummy or bad or scary or sad.

**[F18]** But just like that, it faded to nothing, like an ephemeral pinstroke disappearing as soon as imprinted.

**[F19]** But they danced at different heights, some higher in the sky.

**[F20]** An ocean of liquid metallic hydrogen churns under a haze of gases on Jupiter.

**[F21]** Just imagine how far that starlight traveled just for you to see it.

**[F22]** They are everywhere our telescopes can see, strewn upon space and arranged into giant groupings of galaxies.

**[F23]** Off the coast of Portugal, waves rising as eyes, hills are rolling calmly toward the shore.

**[F24]** That's happening right now, as we sit here.

**[F25]** It is swirling in lakes, swelling in oceans, and evaporating in the skies.

**[F26]** harmony of living things dwelling at every mountain peak and ocean floor.

**[F27]** Humpback whales are wandering in murky serenity, sweeping and rolling, wise and graceful.

**[F28]** They are seeing sights thinking thoughts.

**[F29]** and fathers are singing lullabies to newborn sons and daughters.

**[F30]** A student is learning the language.

**[F31]** Someone is daydreaming under the cover of clouds.

**[F32]** At this precise second, someone out there is seeing the shapes of animals in clouds.

**[F33]** Someone else is blowing out candles on a cake.

**[F34]** Someone else is playing with a tiger cub.

**[F35]** Think of the thousands of languages being spoken.

**[F36]** We can't be sure who or where.

**[F37]** Her eyelids heavy, her breath soft deep.

**[F38]** Grandpa guided her back inside, up the stairs into her room.

**[F39]** She thought of porch lights rippling on water comets sailing around the sun.

**[F40]** So he drifted off to the soundest of sleeps the sweetest of dreams.
