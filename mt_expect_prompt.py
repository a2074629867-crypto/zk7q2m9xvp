# -*- coding: utf-8 -*-
"""mt_expect_prompt.py —— 生成「旁白停顿期望表」的 LLM 判档任务书。

设计要点：
1. **句末默认 clause，不问 LLM。** 马修母带实测句号位置 99% 都停，中位 1.58s，
   没有第二种可能。问 LLM 只会引入噪声。只有逗号需要判 inner/bound。
2. **不给时长。** 给 base 值（0.51/1.135）会让 LLM 往数字上靠。只给句法判据。
3. **不判「该不该停」。** 母带实测 96% 的逗号都停，所以不存在省略档。
   LLM 只需回答「这个逗号是成分内缝还是成分间缝」。
4. 输出骨架 JSON 的键是 `句子id.pause序号`，与生产链 pause_llm.json 对齐。

用法：
  python mt_expect_prompt.py --src _ch1_sents.txt --out _ch1_expect_task.md --skeleton _ch1_expect_skel.json
"""
import argparse
import json
import re

TIER_BASE = {'inner': 0.51, 'bound': 1.135, 'clause': 1.695}


def parse_sents(path):
    out = []
    for line in open(path, encoding='utf-8'):
        m = re.match(r'\[([A-Za-z]?\d+)\]\s*\(\s*(\d+)词\)\s*(.+)', line.strip())
        if not m:
            continue
        sid, nw, text = m.group(1), int(m.group(2)), m.group(3).strip()
        # 找逗号位置（第几个逗号）与它前面的词
        commas = []
        k = 0
        for i, ch in enumerate(text):
            if ch == ',':
                k += 1
                before = text[:i].rstrip()
                word = before.split()[-1] if before.split() else ''
                after = text[i + 1:].lstrip()
                nxt = after.split()[0] if after.split() else ''
                commas.append(dict(idx=k, left=word, right=nxt,
                                   ctx=text[max(0, i - 45):i + 45]))
        out.append(dict(sid=sid, nw=nw, text=text, commas=commas))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=r'G:/_setup/_ch1_sents.txt')
    ap.add_argument('--out', default=r'G:/_setup/_ch1_expect_task.md')
    ap.add_argument('--skeleton', default=r'G:/_setup/_ch1_expect_skel.json')
    ap.add_argument('--max-sent', type=int, default=0)
    a = ap.parse_args()

    sents = parse_sents(a.src)
    if a.max_sent:
        sents = sents[:a.max_sent]
    n_comma = sum(len(s['commas']) for s in sents)
    print('句 %d，逗号 %d' % (len(sents), n_comma))

    # ---- 骨架
    skel = {}
    for s in sents:
        if not s['commas']:
            continue
        skel[s['sid']] = {str(c['idx']): {'tier': None, 'why': ''} for c in s['commas']}
    json.dump(skel, open(a.skeleton, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('骨架 → %s（%d 句 / %d 逗号）' % (a.skeleton, len(skel), n_comma))

    # ---- 任务书
    L = []
    A = L.append
    A('# 旁白停顿判档任务（马修规则 v2）\n')
    A('## 你要做什么\n')
    A('给下面 %d 个句子里**每一个逗号**判一个档位：`inner` 还是 `bound`。\n' % len(sents))
    A('**句末句号不用判**，已默认 `clause`。\n')
    A('## 背景（为什么只判逗号）\n')
    A('这是《Wonder》有声书旁白母带的实测结论：')
    A('- 218 个逗号位置，96% 都有 ≥0.12s 的停顿，中位 1.16s')
    A('- 143 个句号位置，99% 都有停顿，中位 1.58s')
    A('- 2149 个非标点词间位置，只有 1.5% 有 ≥0.3s 停顿（换气）')
    A('\n⇒ **停顿位置完全由标点决定，不存在"该不该停"的问题。**')
    A('你只需要回答：这个逗号切开的，是**一个成分的内部**，还是**两个成分之间**。\n')
    A('## 两个档位\n')
    A('| tier | 判据 |')
    A('|---|---|')
    A('| `inner` | 逗号切开的**是同一个成分的内部**。后半是前半中某个词的修饰语/补足语。'
      '<br>典型：中心词←介词短语（`a memory, of a boy` 不是这种，见下）'
      '<br>真正典型：名词←分词（`penguins, huddling together`）、动词←介词短语（`fall, into the pillow`）、'
      '主语←谓语（`the moment, was stretching`）、限定词←名词（`this, very instant`）、'
      '并列短语内部（`from big, to tiny`、`crummy or bad, or scary`）'
      '<br>**测试：问"后半在修饰前半的哪个词？"——能明确点名 → inner** |')
    A('| `bound` | 逗号切开的是**两个不同成分**。后半不修饰前半任何词。'
      '<br>典型：并列项之间（`Green birds, blue bears, and red fish`）、同位语引入（`her favorite animal, Snug the dinosaur`）、'
      '插入语闭合后回主句（`In this moment, Grandpa continued, our planet...`）、前置状语后接主句（`In Venezuela, a gentle flow...`）、'
      '独立主格另起（`Her eyelids heavy, her breath soft`）、逗号分隔的分词状语（`sat in silence, letting the universe unfold`）'
      '<br>**测试：问"后半在修饰前半的哪个词？"——答不出，它是并列/同位/新成分 → bound** |')
    A('\n**没有第三档。** 不存在 `drop`（不停）或 `beat`（情绪落点）：')
    A('母带实测证明马修在每个逗号都停，且旁白没有情绪落点。判成这两种会直接算错。\n')
    A('## 判定顺序（每条逗号按顺序问）\n')
    A('1. 后半能独立成一个成分吗？不能，且它在修饰前半某个词 → `inner`')
    A('2. 能独立成成分，或它不修饰前半任何词（并列/同位/新成分） → `bound`\n')
    A('## 反例（最容易标错的三类）\n')
    A('- `the depth, of this planet` → `inner`。`of this planet` 修饰 `depth`。')
    A('- `the intensities, some short bursts of light` → `bound`。同位语，不修饰 `intensities` 这个词。')
    A('- `poets, penning verses` → `inner`。分词 `penning` 修饰 `poets`（独立主格）。')
    A('- `poets penning verses, farmers picking berries` → `bound`。两个独立主格并列。')
    A('- `He fell into the pillow, and the dinosaur bumped` → `bound`。并列分句。')
    A('- `sat in silence for a few minutes, letting the universe unfold` → `bound`。逗号分隔的分词状语，是新成分。')
    A('- `an adorable tortoise, named Jonathan` → `inner`。`named Jonathan` 是后置定语。\n')
    A('## 输出格式\n')
    A('纯 JSON（不要代码块围栏、不要注释），写到指定路径。键是句子 id，值是逗号序号 → 档位：\n')
    A('```')
    A('{')
    A('  "000": {"1": {"tier": "bound", "why": "which 引导定语从句"}},')
    A('  "005": {"1": {"tier": "inner", "why": "from big 与 to tiny 同属 from...to"}}')
    A('}')
    A('```\n')
    A('`why` 用中文，≤15 字，**必须点名具体词或结构**。')
    A('只输出骨架里出现的句子 id 和逗号序号，不要多也不要少。\n')
    A('## 待判文本（%d 句 / %d 个逗号）\n' % (len(sents), n_comma))
    for s in sents:
        if not s['commas']:
            continue
        A('**[%s]** %s\n' % (s['sid'], s['text']))
        for c in s['commas']:
            A('　　· 逗号%s：`%s` ‖ `%s`' % (c['idx'], c['left'], c['right']))
        A('')
    open(a.out, 'w', encoding='utf-8').write('\n'.join(L))
    print('任务书 → %s' % a.out)


if __name__ == '__main__':
    main()
