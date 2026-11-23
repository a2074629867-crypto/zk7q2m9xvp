# -*- coding: utf-8 -*-
'''_ann_mkjobs.py -- 生成铺量用的任务卡（每个执行体读自己那一张）。

为什么用任务卡：48 批 × 3 路 = 144 个批次产出，逐个写内联提示调不一。
卡里只写“读哪些批、写到哪、什么格式、怎么自查”，规则本身仍在任务包 prompt 里（单一来源）。
'''
import glob
import os

ROOT = 'G:/_setup'
TASKS = os.path.join(ROOT, '_ann', 'tasks_tier_full')
JOBS = os.path.join(ROOT, '_ann', 'jobs')
OUT = os.path.join(ROOT, '_ann', 'out_full')
PER = 6

CARD = '''# 标注任务：{track_cn} {first} ~ {last}（{n} 批）

你要把 {n} 个任务包逐批标完，每批写一个结果文件。全部做完再回报。

## 一、要读的任务包

{srcs}

每个文件的字段：
- `prompt` —— 标注规则，**必须逐条遵守**；「一、停顿」是判定阶梯，按顺序命中第一条就停。
- `items` —— 待标注句。每条有 `sid` / `text` / `tokens` / `slots` / `prev` / `next`。
- `slots[].bid` 是唯一合法的停顿 id；`slots[].left` / `right` 是标点左右两段原文（`right` 可能是空串）。

## 二、要写的结果文件

{outs}

每个结果文件内容（只写这一个 JSON，不要代码块、不要注释、不要额外说明）：

```
{{"items":[
  {{"sid":"c1_0001",
   "pause":[{{"bid":"c1_0001#1","tier":"mid","why":"右段有主谓→分句"}}],
   "stress":[{{"tok":3,"level":2,"why":"时间对比"}}],
   "rate":{{"rate":0.78,"why":"祖母去世，回忆段落"}}}}
]}}
```

注意：
- `rate` **必须是对象或 `null`**。写成裸数字 `0.78` 会被下游静默丢弃，算错。
- `stress` 每条最多 3 个，`tok` 是 `tokens` 下标（0 起）。
- `pause` 的 `bid` 必须逐个照抄 `slots[].bid`，不能自己编号、不能漏、不能多。
- 没槽位的句子写 `"pause":[]`；不需要慢读写 `"rate":null`。

## 三、写完必须自查

每批写完跑一次（把批次名换成本批）：

```
G:/Python310/python.exe G:/_setup/_ann_check_one.py --dir {outdir} --batches {batchlist}
```

全部打印 `[OK ]` 才算完成。出现 `[BAD]` 就按提示改对应文件，改完重跑，直到全 OK。

## 四、不要做的事

- 不要改任务包，不要碰 `{outdir}` 以外的目录。
- 不要用后面批次的结果覆盖前面批次。
- 不要只写一部分就回报。

完成后回报：处理批复数、总槽位数、每批 short/mid/long（或 zero/short/mid/long）分布、自查是否全 OK。
'''


def main():
    os.makedirs(JOBS, exist_ok=True)
    batches = sorted(os.path.basename(p) for p in glob.glob(os.path.join(TASKS, 'batch_*.json')))
    narr = [b for b in batches if b <= 'batch_0036.json']
    dlg = [b for b in batches if b > 'batch_0036.json']
    print('narr %d 批, dlg %d 批' % (len(narr), len(dlg)))

    cards = []
    for model in ('ds', 'hy4', 'hy3'):
        for trk, lst, cn in (('narr', narr, '旁白'), ('dlg', dlg, '对白')):
            for ci in range(0, len(lst), PER):
                chunk = lst[ci:ci + PER]
                outdir = os.path.join(OUT, trk, model)
                name = '%s_%s_%02d.md' % (trk, model, ci // PER + 1)
                body = CARD.format(
                    track_cn=cn, first=chunk[0], last=chunk[-1], n=len(chunk),
                    srcs='\n'.join('- `%s`' % os.path.join(TASKS, b).replace('\\', '/') for b in chunk),
                    outs='\n'.join('- `%s`' % os.path.join(outdir, b).replace('\\', '/') for b in chunk),
                    outdir=outdir.replace('\\', '/'),
                    batchlist=' '.join(b.replace('.json', '') for b in chunk))
                p = os.path.join(JOBS, name)
                open(p, 'w', encoding='utf-8').write(body)
                cards.append((name, model, trk, len(chunk)))

    for c in cards:
        print('  %-22s model=%-4s track=%-4s 批数=%d' % c)
    print('共 %d 张任务卡 -> %s' % (len(cards), JOBS))


if __name__ == '__main__':
    main()
