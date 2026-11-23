# -*- coding: utf-8 -*-
"""mt_matt_annot2_export.py —— 马修旁白停顿第二轮盲标（句内二分）。

与第一轮的区别（第一轮的教训）：
1. 第一轮 tight 覆盖 0.31~1.91s（跨 6 倍），三方对它的判定也分裂。
   事后按 main 标注 + 实测时长排序，发现 **0.61~0.97 完全空档**，
   两侧是两种不同句法结构：
     A 成分内缝  0.31~0.61（主谓之间 / 名词+分词 / 动词+介词短语 / 限定词+名词）
     B 成分间缝  0.97~1.91（并列项 / 同位语 / 插入语闭合后 / 总述后接列举）
   ⇒ 本轮把 tight 拆成 inner / bound，判据换成**纯句法**（"后半在修饰前半的哪个词"）。

2. 第一轮 40 条太少，句内只有 20 条，Kappa 置信区间过宽。本轮 60 条。

3. 第一轮 drop/beat 被滥用（hy4 判 12 条 drop，实测中位 1.53s）。本轮**取消**这两档。

4. 仍然**不给时长**。给了就锚定，标完再按时长分组才有验证价值。

输出 _matt_annot2_samples.json + _matt_annot2_task.md
"""
import json
import sys

import numpy as np

sys.path.insert(0, r'G:/_setup')

MINED = r'G:/_setup/matt_pause_mined.json'
WORDS = r'G:/_setup/_matt_asr_words.json'
OUT_S = r'G:/_setup/_matt_annot2_samples.json'
OUT_T = r'G:/_setup/_matt_annot2_task.md'
CTX = 8
PER_LAYER = 15

LAYERS = [(0.30, 0.65), (0.65, 1.00), (1.00, 1.50), (1.50, 2.60)]


def load_words():
    d = json.load(open(WORDS, encoding='utf-8'))
    out = []
    for a, b, w in d:
        if b < a:
            a, b = b, a
        out.append(dict(t0=float(a), t1=float(b), w=w))
    out.sort(key=lambda r: r['t0'])
    return out


def main():
    recs = json.load(open(MINED, encoding='utf-8'))['recs']
    words = load_words()
    n0 = len(words)
    words = [w for w in words if w['t1'] - w['t0'] <= 1.5]
    print('剔除异常宽词 %d 个（>1.5s），剩 %d' % (n0 - len(words), len(words)))
    t0s = np.array([w['t0'] for w in words])
    t1s = np.array([w['t1'] for w in words])
    mids = (t0s + t1s) / 2.0

    rows = []
    for r in recs:
        s, e, g = r['s'], r['e'], r['gap']
        if not (0.30 <= g <= 2.60):
            continue
        mid = (s + e) / 2.0
        ip = int(np.searchsorted(mids, mid, side='left') - 1)
        inx = int(np.searchsorted(mids, mid, side='left'))
        if ip < CTX or inx + CTX > len(words) or inx <= ip:
            continue
        before = [words[k]['w'] for k in range(ip - CTX + 1, ip + 1)]
        after = [words[k]['w'] for k in range(inx, inx + CTX)]
        rows.append(dict(gap=g, before=before, after=after))
    print('可用样本 %d（前后各 %d 词）' % (len(rows), CTX))

    rng = np.random.default_rng(20261030)
    picked = []
    for lo, hi in LAYERS:
        cand = [r for r in rows if lo <= r['gap'] < hi]
        print('  %.2f~%.2f: %d 条' % (lo, hi, len(cand)))
        if len(cand) <= PER_LAYER:
            picked += cand
        else:
            idx = rng.choice(len(cand), PER_LAYER, replace=False)
            picked += [cand[i] for i in sorted(idx)]

    order = rng.permutation(len(picked))
    picked = [picked[i] for i in order]

    samples = []
    for i, r in enumerate(picked):
        samples.append(dict(
            key='Q%03d' % (i + 1),
            text=' '.join(r['before']) + ' [PAUSE] ' + ' '.join(r['after']),
            _gap=r['gap']))
    json.dump(samples, open(OUT_S, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n导出 %d 条 → %s' % (len(samples), OUT_S))

    # ---------- 任务书 ----------
    L = []
    A = L.append
    A('# 旁白停顿句法标注（马修母带 · 第二轮 · 盲标）\n')
    A('你是三方交叉验证中的一票。**独立判断。不要猜"标准答案"，也不要猜停顿有多长。**\n')
    A('## 素材\n')
    A('《Wonder》有声书旁白（男声，睡前故事语调，107wpm）。每一条是一段连续文本，')
    A('中间 `[PAUSE]` 标出一处**真实存在的停顿**。判断这处停顿的**句法性质**。\n')
    A('> **不要估算时长。** 我们刻意不给时长——给了就会锚定。你只判结构，时长我们事后统计。\n')
    A('## 只有四档\n')
    A('| kind | 判据 |')
    A('|---|---|')
    A('| `inner` | **停顿切开的是同一个成分的内部。** 后半是前半中某个词的**修饰语/补足语**。'
      '<br>典型：中心词 ← 介词短语（`a memory \\| of a boy`）、名词 ← 分词（`penguins \\| huddling`）、'
      '动词 ← 介词短语（`fall \\| into the pillow`）、主语 ← 谓语（`the moment \\| was stretching`）、'
      '限定词 ← 名词（`this \\| very instant`）'
      '<br>**测试：问"后半在修饰前半的哪个词？"——能明确答出那个词 → inner** |')
    A('| `bound` | **停顿切开的是两个不同成分，但这句话还没说完。**'
      '<br>典型：并列项之间（`bears \\| and red fish`）、同位语引入（`intensities \\| some short bursts`）、'
      '插入语闭合后回主句（`he said \\| Grandpa \\| ...`）、总述后接列举、前置状语后接主句'
      '<br>**测试：问"后半在修饰前半的哪个词？"——答不出具体词，它是并列/同位/新成分 → bound** |')
    A('| `clause` | **一句话说完了。** 停顿前后是两个可以各自独立的句子/分句。'
      '<br>这是句末的默认档。`...echoed across the lake. \\| Venus abided in the sky` |')
    A('| `para` | **话题/场景/视角切换。** 不只是句子结束，是"换了一段"。'
      '<br>判据：前一句和后一句讲的**不是同一件事**（时间跳、地点跳、叙述→内心独白） |')
    A('\n**已取消的两档，不要使用：** `drop`（"不停也行"）和 `beat`（"情绪落点"）。')
    A('上一轮实测证明马修在每个标点位置都停，且旁白没有情绪落点。判成这两档会直接算错。\n')
    A('## 判定顺序（必须按顺序，每条问一遍）\n')
    A('1. **后半能独立成句吗？** 不能，且它在修饰前半某个词 → `inner`')
    A('2. 不能独立成句，但它不修饰前半任何词（是并列/同位/新成分） → `bound`')
    A('3. 能独立成句，且和前半讲同一件事 → `clause`')
    A('4. 能独立成句，且换了话题/场景/视角 → `para`\n')
    A('## 反例（上一轮标错的）\n')
    A('- `the depth [PAUSE] of this planet` → `inner`。`of this planet` 修饰 `depth`。')
    A('- `pinstroke [PAUSE] disappearing into the folds` → `inner`。分词修饰 `pinstroke`。')
    A('- `the intensities [PAUSE] some short bursts of light` → `bound`。同位语，不修饰 `intensities` 这个词本身。')
    A('- `He fell into the pillow [PAUSE] and the dinosaur bumped` → `bound`。并列项之间。')
    A('- `...a full sentence. [PAUSE] Then a new thought` → `clause`，**不是** `inner`——句末不能用 inner。')
    A('- `call of a loon echoed across the lake. [PAUSE] Venus abided in the sky` → `clause`。')
    A('- 若前后讲的是不同场景/时间 → 才升 `para`。\n')
    A('## 输出格式\n')
    A('纯 JSON（不要代码块围栏、不要注释），写到指定路径：\n')
    A('```')
    A('{')
    A('  "Q001": {"kind": "inner", "why": "of a boy 修饰 memory"},')
    A('  "Q002": {"kind": "bound", "why": "并列宾语之间"}')
    A('}')
    A('```\n')
    A('`why` 用中文，≤20 字，**必须点名你依据的那个词或那个结构**。\n')
    A('## 待标样本（%d 条）\n' % len(samples))
    for s in samples:
        A('**%s**  %s\n' % (s['key'], s['text']))
    open(OUT_T, 'w', encoding='utf-8').write('\n'.join(L))
    print('写出任务书 → %s' % OUT_T)

    gs = np.array([s['_gap'] for s in samples])
    print('\n（不外露）实际 gap: p10 %.2f p50 %.2f p90 %.2f' % (
        np.percentile(gs, 10), np.median(gs), np.percentile(gs, 90)))


if __name__ == '__main__':
    main()
