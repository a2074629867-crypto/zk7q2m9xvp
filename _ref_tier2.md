# 情绪两档：按**唤醒度**切（普通 / 激烈）

> 强度主尺 = vox **arousal**（0.70）+ ΔF0 半音（0.30），**角色内**标准化。
> 不用自己拍的 F0/RMS/wpm 加权：实测 `Charles angry` 三个量方向相反（F0↑ RMS↓ wpm↑），
> 手工权重一加就抵消成「差 0.00」。arousal 是心理学标准的「激烈程度」维度。
> 也不按 z 分：z 是「参考在情绪空间里的位置」，不是强度（Thomas calm 4 档 z 跨度仅 0.09）。
> 算 arousal 前已归一到 voiced RMS −24dBFS（参考素材原始电平 −23~−48dBFS 不等）。

## 一、分档结果

| 角色 | 情绪 | 档数 | 普通档 | 激烈档 | 强度差 |
|---|---|---|---|---|---|
| Charles | angry | 2 | Charles_angry_2 (0.49) | c000 (0.74) | +0.24 |
| Charles | defiant | 2 | c257 (0.74) | c326 (1.26) | +0.52 |
| Charles | excited | 4 | Charles_excited_4 (-0.06) | c000 (1.37) | +1.43 |
| Charles | nervous | 2 | Charles_nervous_2 (0.28) | c246 (0.47) | +0.19 |
| Charles | neutral | 4 | c000 (-0.38) | Charles_neutral_4 (0.56) | +0.95 |
| Charles | soft | 3 | c000 (-1.80) | c000 (-1.21) | +0.59 |
| Charles | wary | 3 | c188 (0.28) | Charles_wary_3 (0.46) | +0.18 |
| Charles | wronged | 3 | Charles_wronged_3 (-1.45) | Charles_wronged_2 (-1.41) | +0.05 |
| Fielding | defiant | 3 | Fielding_defiant_c153 (0.38) | Fielding_defiant_c078 (1.26) | +0.89 |
| Fielding | excited | 3 | Fielding_excited_c369 (0.40) | Fielding_excited_c303 (0.50) | +0.10 |
| Fielding | nervous | 3 | Fielding_nervous_c728 (0.18) | Fielding_nervous_c100 (0.88) | +0.70 |
| Fielding | wary | 3 | Fielding_wary_c049 (-1.17) | Fielding_wary_c301 (0.08) | +1.25 |
| Fielding | wronged | 3 | Fielding_wronged_c046 (-1.41) | Fielding_wronged_c364 (-0.94) | +0.47 |
| Helena | defiant | 3 | Helena_defiant_c127 (0.56) | Helena_defiant_c390 (1.45) | +0.90 |
| Helena | excited | 3 | Helena_excited_c144 (0.48) | Helena_excited_c466 (0.86) | +0.38 |
| Helena | nervous | 3 | Helena_nervous_c441 (-0.31) | Helena_nervous_c405 (0.38) | +0.69 |
| Helena | wary | 3 | Helena_wary_c073 (-0.93) | Helena_wary_c124 (0.49) | +1.41 |
| Helena | wronged | 3 | Helena_wronged_c497 (-2.21) | Helena_wronged_c083 (-0.91) | +1.30 |
| Joseph | defiant | 3 | Joseph_defiant_c030 (-0.45) | Joseph_defiant_c002 (1.21) | +1.67 |
| Joseph | excited | 3 | Joseph_excited_c028 (0.34) | Joseph_excited_c006 (1.08) | +0.73 |
| Joseph | nervous | 3 | Joseph_nervous_c056 (0.16) | Joseph_nervous_c058 (0.90) | +0.74 |
| Joseph | normal | 3 | Joseph_normal_c748 (-0.75) | Joseph_normal_c1016 (-0.08) | +0.66 |
| Joseph | wary | 3 | Joseph_wary_c020 (-0.75) | Joseph_wary_c035 (0.18) | +0.94 |
| Joseph | wronged | 3 | Joseph_wronged_c042 (-1.62) | Joseph_wronged_c017 (-1.27) | +0.35 |
| Thomas | begging | 4 | c000 (-0.73) | c000 (0.97) | +1.69 |
| Thomas | calm | 4 | c000 (-1.14) | c000 (-0.90) | +0.24 |
| Thomas | defiant | 3 | Thomas_defiant_1 (0.46) | Thomas_defiant_3 (1.26) | +0.80 |
| Thomas | excited | 1+代理 | Thomas_excited_1 (0.81) | Thomas_defiant_3 (0.84, 代理) | +0.08 |
| Thomas | loud | 5 | Thomas_loud_5 (-0.69) | c000 (1.24) | +1.93 |
| Thomas | nervous | 2 | c187 (0.33) | c230 (0.77) | +0.44 |
| Thomas | scold | 3 | c000 (-0.66) | c000 (0.07) | +0.72 |
| Thomas | wary | 3 | Thomas_wary_1 (-0.72) | Thomas_wary_3 (-0.35) | +0.37 |
| Thomas | wronged | 3 | Thomas_wronged_2 (-1.17) | c009 (-0.73) | +0.43 |

> **代理档（2026-11-15 12:2x）**：`Thomas excited` 原生只有 1 条（arousal 0.760）。
> 按用户要求「找最相近的」，在 Thomas 自己的 28 条参考里按 vox 情绪向量
> (valence, dominance) 找最近邻、且 arousal 至少 +0.08 的：
> → **Thomas_defiant_3**（*Il est riche et vous êtes pauvres…*，arousal 0.844，距离 0.101）。
> 更近的一条是 loud `On sera jamais prêts pour ce soir!`（距离 0.074）但 arousal 只 +0.013，
> 听不出强度差，等于没分档，已排除。工具 `_tier_excited_nn.py`，明细 `_tier_excited_nn.json`。
> Thomas 池子的唤醒度上限就是 0.857（begging `La chambre de mon oncle!`），
> 真要有「更激动的兴奋」只能从原剧补切。

## 二、强度明细（每档的声学量）

### Charles / angry（2 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Charles_angry_2 | 0.49 | 0.6816 | 312.3 | 1.69 | -30.5 | 164.7 | 2.55 | C'est pas moi. Je vous le jure! |
| intense | c000 | 0.74 | 0.8291 | 271.1 | -0.76 | -23.2 | 127.1 | 6.61 | Il a pissé dans sa culotte, le bébé! J'aurais dû te laisser  |

### Charles / defiant（2 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c257 | 0.74 | 0.8291 | 271.1 | -0.76 | -23.2 | 127.1 | 6.61 | Il a pissé dans sa culotte, le bébé! J'aurais dû te laisser  |
| intense | c326 | 1.26 | 0.9457 | 323.4 | 2.3 | -21.1 | 212.3 | 4.24 | Je t'ai dit de disparaître. Tu entends, Thomas? Je ne veux p |

### Charles / excited（4 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Charles_excited_4 | -0.06 | 0.5433 | 269.2 | -0.88 | -33.1 | 95.9 | 4.38 | Eh bien, Thomas, vous oubliez nos accords? |
| intense | c000 | 1.37 | 0.9035 | 395.3 | 5.77 | -23.4 | 227.8 | 3.95 | Menteur! Ton père n'est rien du tout! Il plaît pas à ma mère |

### Charles / nervous（2 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Charles_nervous_2 | 0.28 | 0.5603 | 346.8 | 3.51 | -31.3 | 147.7 | 3.25 | Maman, viens voir. Je crois que c'est lui. |
| intense | c246 | 0.47 | 0.6352 | 343.3 | 3.33 | -38.6 | 105.7 | 5.11 | T'as raison. Il vaut mieux que je te tue. |

### Charles / neutral（4 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c000 | -0.38 | 0.4323 | 263.6 | -1.24 | -33.3 | 202.5 | 2.37 | Elle a fait un bébé dans le train. |
| intense | Charles_neutral_4 | 0.56 | 0.6684 | 342.3 | 3.28 | -28.9 | 125.0 | 1.92 | J'en ai pas besoin. |

### Charles / soft（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c000 | -1.80 | 0.0788 | 178.6 | -7.98 | -34.9 | 228.3 | 1.84 | Tu peux plus rien me faire, maintenant. |
| intense | c000 | -1.21 | 0.307 | 173.5 | -8.48 | -27.5 | 194.8 | 1.54 | Mais il pouvait rien m'arriver. |

### Charles / wary（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c188 | 0.28 | 0.6657 | 270.3 | -0.81 | -26.7 | 143.7 | 5.01 | Il fallait pas me suivre. Et quand on marche, on la boucle. |
| intense | Charles_wary_3 | 0.46 | 0.6928 | 295.2 | 0.72 | -32.3 | 65.2 | 2.76 | Si, c'est vrai. |

### Charles / wronged（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Charles_wronged_3 | -1.45 | 0.217 | 174.0 | -8.43 | -31.2 | 150.0 | 2.0 | Maman, j'aurai plus jamais peur. |
| intense | Charles_wronged_2 | -1.41 | 0.1471 | 214.2 | -4.83 | -50.0 | 115.6 | 4.67 | De tous les gens, c'est moi que tu préfères? |

### Fielding / defiant（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Fielding_defiant_c153 | 0.38 | 0.5891 | 205.7 | 0.8 | -30.1 | 124.0 | 7.26 | I swear to God, if you tell anyone I'm making this film, I'l |
| intense | Fielding_defiant_c078 | 1.26 | 0.7225 | 241.4 | 3.57 | -28.4 | 217.6 | 3.86 | Had to be the one with the bloody trailer on the back, didn' |

### Fielding / excited（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Fielding_excited_c369 | 0.40 | 0.5716 | 216.1 | 1.65 | -33.0 | 173.9 | 2.76 | We've got ten minutes before lessons. Let's go. |
| intense | Fielding_excited_c303 | 0.50 | 0.6386 | 196.4 | 0.0 | -36.8 | 193.5 | 4.03 | No. He could if he wanted to, though. He's pretty skill at e |

### Fielding / nervous（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Fielding_nervous_c728 | 0.18 | 0.5669 | 195.4 | -0.09 | -26.8 | 130.4 | 3.22 | My brother is the worst actor ever. |
| intense | Fielding_nervous_c100 | 0.88 | 0.5717 | 277.3 | 5.97 | -29.3 | 144.3 | 5.82 | You know, I've been thinking. The watch is nice, but, well,  |

### Fielding / wary（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Fielding_wary_c049 | -1.17 | 0.2711 | 188.1 | -0.75 | -35.8 | 118.8 | 3.03 | Didn't you know? About the torture? |
| intense | Fielding_wary_c301 | 0.08 | 0.5584 | 188.9 | -0.67 | -34.6 | 189.3 | 3.17 | their bone goes up through their brain and kills 'em. |

### Fielding / wronged（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Fielding_wronged_c046 | -1.41 | 0.2369 | 179.4 | -1.57 | -35.1 | 192.3 | 4.68 | But, er, if I do, you, er, might have to give me something i |
| intense | Fielding_wronged_c364 | -0.94 | 0.2967 | 200.4 | 0.35 | -44.0 | 221.7 | 4.06 | You, er, left your alarm clock in my locker. You'd better go |

### Helena / defiant（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Helena_defiant_c127 | 0.56 | 0.6719 | 246.7 | 1.2 | -32.6 | 105.0 | 8.0 | Yeah, it was a bit unsettling, to be honest. Well, you're he |
| intense | Helena_defiant_c390 | 1.45 | 0.7589 | 343.6 | 6.93 | -32.5 | 134.6 | 7.58 | it's taken me three hours to get I left home at two I can as |

### Helena / excited（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Helena_excited_c144 | 0.48 | 0.6773 | 230.2 | 0.0 | -32.0 | 105.6 | 8.52 | Did Jerry tell you about me getting a car, Tom? Yes. What do |
| intense | Helena_excited_c466 | 0.86 | 0.7508 | 238.0 | 0.58 | -35.9 | 156.5 | 5.75 | You should come out and have a drink with us sometime, me an |

### Helena / nervous（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Helena_nervous_c441 | -0.31 | 0.4535 | 267.8 | 2.62 | -35.0 | 129.9 | 2.31 | I don't really smoke normally |
| intense | Helena_nervous_c405 | 0.38 | 0.6014 | 271.4 | 2.85 | -35.3 | 217.3 | 3.59 | I know Joey but you're allowed a couple glasses aren't you T |

### Helena / wary（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Helena_wary_c073 | -0.93 | 0.4816 | 163.7 | -5.9 | -34.1 | 282.1 | 2.34 | It's not all Rosy. I have good days and bad days. |
| intense | Helena_wary_c124 | 0.49 | 0.632 | 265.1 | 2.44 | -34.2 | 216.9 | 4.15 | Oh. I'm sorry, I've just had to have a cigarette, and I know |

### Helena / wronged（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Helena_wronged_c497 | -2.21 | 0.199 | 163.5 | -5.92 | -48.7 | 201.3 | 4.47 | I do feel a bit guilty, though, but at the end of the day. S |
| intense | Helena_wronged_c083 | -0.91 | 0.4306 | 192.8 | -3.07 | -36.5 | 186.0 | 2.58 | plastic bags, and shove them under the bed. |

### Joseph / defiant（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_defiant_c030 | -0.45 | 0.487 | 103.6 | -1.47 | -29.5 | 105.9 | 3.4 | Angela felt why drag it out. |
| intense | Joseph_defiant_c002 | 1.21 | 0.6566 | 136.4 | 3.29 | -22.5 | 125.3 | 4.79 | I knew that all my life I'd wanted his embrace |

### Joseph / excited（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_excited_c028 | 0.34 | 0.5803 | 115.6 | 0.42 | -26.7 | 146.6 | 5.32 | You can love somebody and want to leave them at the same tim |
| intense | Joseph_excited_c006 | 1.08 | 0.6862 | 122.9 | 1.48 | -23.4 | 171.4 | 3.85 | I suppose I was half dazzled by her in the beginning. |

### Joseph / nervous（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_nervous_c056 | 0.16 | 0.4986 | 126.1 | 1.93 | -24.2 | 177.8 | 2.7 | I think you want something I haven't got. |
| intense | Joseph_nervous_c058 | 0.90 | 0.5395 | 152.0 | 5.16 | -24.9 | 164.4 | 2.19 | I'm no good for you, Grace. |

### Joseph / normal（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_normal_c748 | -0.75 | 0.4065 | 108.6 | -0.66 | -28.5 | 120.5 | 2.49 | It's all contactless now, yes. |
| intense | Joseph_normal_c1016 | -0.08 | 0.5623 | 102.6 | -1.64 | -23.4 | 197.8 | 1.82 | My father was a reserved man. |

### Joseph / wary（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_wary_c020 | -0.75 | 0.4556 | 98.8 | -2.29 | -30.3 | 93.1 | 7.09 | All it took was Angela's hand on my arm, her touch. |
| intense | Joseph_wary_c035 | 0.18 | 0.5748 | 110.3 | -0.39 | -28.8 | 133.0 | 4.06 | That makes me feel, well, not much good really. |

### Joseph / wronged（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Joseph_wronged_c042 | -1.62 | 0.2176 | 113.4 | 0.09 | -27.5 | 145.2 | 4.96 | She was looking at me as if she was sorry for me. |
| intense | Joseph_wronged_c017 | -1.27 | 0.2998 | 110.2 | -0.4 | -28.6 | 91.1 | 3.95 | Yes, it's not easy to explain. |

### Thomas / begging（4 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c000 | -0.73 | 0.6833 | 66.7 | -21.03 | -25.4 | 9.0 | 6.67 | Charles! |
| intense | c000 | 0.97 | 0.8567 | 238.2 | 1.0 | -19.9 | 138.9 | 2.16 | La chambre de mon oncle! |

### Thomas / calm（4 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c000 | -1.14 | 0.1759 | 195.3 | -2.44 | -34.5 | 159.6 | 3.76 | Mais il ne s'agit plus de vivre, il faut régner." |
| intense | c000 | -0.90 | 0.2418 | 206.7 | -1.45 | -42.8 | 81.6 | 5.15 | Je t'ai mis ta récompense. Adieu, Charles. |

### Thomas / defiant（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Thomas_defiant_1 | 0.46 | 0.5727 | 325.1 | 6.39 | -47.3 | 83.5 | 5.75 | Mesdames et messieurs, bonsoir. Non. Attends. Je recommence. |
| intense | Thomas_defiant_3 | 1.26 | 0.8437 | 336.7 | 6.99 | -27.8 | 234.0 | 3.59 | Il est riche et vous êtes pauvres. C'est pour ça que vous êt |

### Thomas / excited（1 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Thomas_excited_1 | 0.81 | 0.7602 | 267.6 | 3.02 | -29.1 | 170.7 | 4.92 | Personne te croira! Personne n'écoute les nouveaux. Un nouve |

### Thomas / loud（5 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Thomas_loud_5 | -0.69 | 0.2988 | 219.8 | -0.39 | -35.9 | 125.7 | 5.73 | Tu sais ce qui va arriver? Mon père va te mettre dehors. |
| intense | c000 | 1.24 | 0.8389 | 336.5 | 6.98 | -27.2 | 228.3 | 3.68 | Il est riche et vous êtes pauvres. C'est pour ça que vous êt |

### Thomas / nervous（2 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c187 | 0.33 | 0.6147 | 251.2 | 1.92 | -33.1 | 129.9 | 5.08 | Mais t'es fou! Beaucoup plus! Je commence à avoir des crampe |
| intense | c230 | 0.77 | 0.7331 | 279.6 | 3.78 | -23.9 | 93.3 | 3.86 | Vite, Charles! Je n'en peux plus! |

### Thomas / scold（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | c000 | -0.66 | 0.2972 | 227.1 | 0.18 | -42.2 | 131.0 | 5.04 | Tu me crois, maintenant? Elle dort même pas dans sa chambre. |
| intense | c000 | 0.07 | 0.5765 | 211.9 | -1.02 | -35.7 | 176.9 | 4.07 | Je vais aller réveiller mon père et je vais tout lui dire. |

### Thomas / wary（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Thomas_wary_1 | -0.72 | 0.3097 | 204.9 | -1.6 | -35.4 | 156.5 | 3.45 | Ils te mettront avec moi pour te faire plaisir. |
| intense | Thomas_wary_3 | -0.35 | 0.3964 | 233.5 | 0.66 | -60.5 | 179.1 | 3.35 | Mais il y a un truc que tu sais pas. |

### Thomas / wronged（3 档）

| 档 | name | score | arousal | F0 | ΔF0 | RMS | wpm | 时长 | 文本 |
|---|---|---|---|---|---|---|---|---|---|
| normal | Thomas_wronged_2 | -1.17 | 0.148 | 207.1 | -1.42 | -35.6 | 116.8 | 4.11 | Mais non, maman. Le docteur vous l'a interdit. |
| intense | c009 | -0.73 | 0.2768 | 222.5 | -0.18 | -31.7 | 104.0 | 5.77 | Je sens que sans vous, je ne saurais plus vivre. |

## 三、需要补切素材的（缺激烈档或只有 1 档）

| 角色 | 情绪 | 现有档数 | 原因 |
|---|---|---|---|
| Thomas | excited | 1 | 只有 1 档 |

## 四、必须如实说的局限

1. **两档的音色不同**：条间实测换档落差中位 6.4 半音。用激烈档生成同一角色，
   听感会比普通档「更亮/更高」，这是设计层代价，不是 bug。
2. **强度分是相对量**：角色内标准化，只能排「同角色内谁更激烈」，
   不能跨角色比（Thomas 的激烈 ≠ Charles 的激烈）。
3. **档数少时切分不稳**：2 档只能比大小，无法验证「中间没有第三档」。
   3 档以上才有 fallback 余量。