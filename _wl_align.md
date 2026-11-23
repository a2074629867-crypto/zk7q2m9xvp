# L1 词级旗标 vs 起伏闸门：逐条对齐

样本 955 条（L1 955 / 闸门 955，按 clip id join）**干净 718 (75.2%)**

闸门判定分布：{'PASS': 580, 'UNMEAS': 222, 'WATCH_HIGH': 68, 'WATCH_LOW': 62, 'FIX_HIGH': 19, 'FIX_LOW': 4}

## 1. 韵律组：L1 词级塔平 vs 闸门低带（FIX_LOW+WATCH_LOW）

| | 闸门低带 | 闸门其余 |
|---|---|---|
| **L1 有 FLAT** | 4（命中） | 78（L1 独家） |
| **L1 无 FLAT** | 62（漏） | 811 |

precision 4.9% · recall 6.1% · Cohen κ **-0.02**

L1 报的 82 条里，闸门落在低带的只有 4 条 —— 说明两把尺子测的不是同一个量。

## 2. 闸门 FIX 的构成（看 L1 结构化盲区）

| 类别 | 条数 | L1 有 FLAT | 说明 |
|---|---|---|---|
| FIX_LOW 太平 | 4 | 0 | L1 有对应判据 |
| FIX_HIGH 太陡 | 19 | 1 | L1 **没有**『太陡』判据 |

FIX 条目里的形状旗：{'SHAPE_CUT': 4, 'SHAPE_RISE': 4, 'SHAPE_OCT': 3}（SHAPE_RISE 末段上扬 / SHAPE_CUT 硬切 / SHAPE_OCT 八度伪影 / SHAPE_REV 抖动 —— L1 全部不看）

## 3. 内容组：闸门结构性看不见

L1 报内容问题 124 条，其中闸门判 PASS 的有 **56 条**（45%）。

分类：{'LEAD_REF': 62, 'PACE': 47, 'TRUNC': 22, 'NO_TARGET': 12}

- `c1_0002` cov=100% said='My father was a reserved man I will not live there again unt'
- `c1_0005` cov=100% said='Never really forgave me for not being him You must not be af'
- `c1_0013` cov=99% said='Even all well Mr Hooper had said and coughed he is very ill '
- `c1_0015` cov=100% said='He never really forgave me for not being him Well because yo'
- `c1_0020` cov=100% said='All he looks like Edmund Hooper said is one of his dead old '
- `c1_0027` cov=100% said='My father was a reserved man He said I shall be away in Lond'
- `c1_0031` cov=98% said='Uh Bob we shall be looking into things he said I shall see a'
- `c1_0033` cov=100% said='Um my father was a reserved man You had better not go into t'
- `c1_0034` cov=31% said="Why can 't I go"
- `c1_0037` cov=100% said="By laws I 'm quiet My father was a reserved man and I cannot"
- `c1_0049` cov=98% said='Never really forgave me for not being him but then said no y'
- `c1_0051` cov=100% said='My father was a reserved man Ah well now I shall soon be doi'

## 4. L1 独家报的塔平（闸门 PASS/WATCH_HIGH）前 10 条

| tid | 闸门 | span | L1 flat_run | 文本 |
|---|---|---|---|---|
| c1_0169 | PASS | 16.3 | I/am/not/a | I am not a hard man, he thought, I h |
| c2_0506 | PASS | 13.1 | began/to/come/very | Hooper began to come very slowly dow |
| c3_0562 | PASS | 19.0 | crow/he/had/ever | It was the largest crow he had ever  |
| c1_0019 | PASS | 14.0 | hair/down/to | Everything about him, from the stubb |
| c1_0099 | WATCH_HIGH | 23.9 | am/depressed/by | He thought, I know myself and am dep |
| c1_0100 | PASS | 10.5 | lend/him/both | But now, with his father gone, he co |
| c2_0215 | PASS | 14.5 | board/beside/the | Hooper began to mould plasticine bet |
| c2_0222 | PASS | 19.8 | shape/of/a | The model was humped in the shape of |
| c2_0224 | PASS | 20.0 | his/battle/of | Then he could get on with his Battle |
| c2_0402 | PASS | 17.4 | of/the/way | He was ashamed of the way she had sp |
