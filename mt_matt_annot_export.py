# -*- coding: utf-8 -*-
"""mt_matt_annot_export.py —— 从马修母带导出盲标样本。

设计要点：
1. **不给实测时长**。给了 1.8s 标注者就会判成 paragraph，那是锚定，
   标完再按时长分组看分布才有意义（盲标 → 事后验证）。
2. 位置用 `[PAUSE]` 标记。母带词级 json 标点缺失（562 处里 545 处 prev_punct=None），
   不能靠标点定位。
3. 上下文取前后各 8 词 —— 少于 6 词判不出从句边界，多于 10 词标注者会跑题。
4. 分层抽样：按停顿长短分 4 层各 10 条，避免全是长停顿。

输出 G:/_setup/_matt_annot_samples.json + _matt_annot_task.md
"""
import json
import sys

import numpy as np

sys.path.insert(0, r'G:/_setup')

MINED = r'G:/_setup/matt_pause_mined.json'
# ★ 不能用 wonder_final.json：它是 GSV 切片拼接的，切片边界处词序错乱。
#   实测导出样本出现 `echoed across the [PAUSE] abided in the sky` 这种不通的上下文。
#   ⇒ 用 whisper 词级时间戳（_matt_asr_words.json，small.en word_timestamps）。
WORDS = r'G:/_setup/_matt_asr_words.json'
OUT_S = r'G:/_setup/_matt_annot_samples.json'
OUT_T = r'G:/_setup/_matt_annot_task.md'
CTX = 8


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
    # 过滤 whisper 跨静音的异常词：实测有 9.02s 宽的 'of'（222.82~231.84），
    # 那是把整段静音算进了一个词。宽度 >1.5s 的一律剔除（真词不会超过 1.5s）。
    n0 = len(words)
    words = [w for w in words if w['t1'] - w['t0'] <= 1.5]
    print('剔除异常宽词 %d 个（>1.5s），剩 %d' % (n0 - len(words), len(words)))
    t0s = np.array([w['t0'] for w in words])
    t1s = np.array([w['t1'] for w in words])

    # ★ 对齐必须用「词中点」，不能用「t1 <= 停顿起点」：
    #   VAD 用 -35dB 阈值，语音段结束比 whisper 的词结束晚约 0.26s
    #   （实测 s=1387.52，而最后一个词的 t1=1387.42、下一个词 t1=1387.78）
    #   ⇒ 用 t1<=s 会取到前一个词，把真正的词挤到后面，上下文整体错位。
    mids = (t0s + t1s) / 2.0
    rows = []
    for r in recs:
        s, e, g = r['s'], r['e'], r['gap']
        mid = (s + e) / 2.0
        ip = int(np.searchsorted(mids, mid, side='left') - 1)
        inx = int(np.searchsorted(mids, mid, side='left'))
        if ip < CTX or inx + CTX > len(words) or inx <= ip:
            continue
        before = [words[k]['w'] for k in range(ip - CTX + 1, ip + 1)]
        after = [words[k]['w'] for k in range(inx, inx + CTX)]
        rows.append(dict(gap=g, before=before, after=after,
                         n_before=CTX, n_after=CTX))
    print('可用样本 %d（要求前后各 %d 词）' % (len(rows), CTX))

    # 分层：4 层各取 10
    layers = [(0.30, 0.60), (0.60, 1.20), (1.20, 2.00), (2.00, 99)]
    picked = []
    rng = np.random.default_rng(42)
    for lo, hi in layers:
        cand = [r for r in rows if lo <= r['gap'] < hi]
        print('  %.2f~%.2f: %d 条' % (lo, hi, len(cand)))
        if len(cand) <= 10:
            picked += cand
        else:
            idx = rng.choice(len(cand), 10, replace=False)
            picked += [cand[i] for i in sorted(idx)]

    # 打乱顺序（避免标注者从时长顺序里猜）
    order = rng.permutation(len(picked))
    picked = [picked[i] for i in order]

    samples = []
    for i, r in enumerate(picked):
        key = 'P%03d' % (i + 1)
        samples.append(dict(key=key,
                            text=' '.join(r['before']) + ' [PAUSE] ' + ' '.join(r['after']),
                            _gap=r['gap']))   # 下划线开头 = 不外露给标注者

    json.dump(samples, open(OUT_S, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n导出 %d 条 → %s' % (len(samples), OUT_S))

    # ---- 写任务书（不含时长）
    lines = []
    lines.append('# 旁白停顿语义标注（马修母带，盲标）\n')
    lines.append('这是三方交叉验证中的一票。**独立判断，不要猜测"标准答案"。**\n')
    lines.append('## 背景\n')
    lines.append('素材是《Wonder》有声书的旁白朗读（男声，睡前故事语调，107wpm）。')
    lines.append('每一条给出一段连续文本，中间用 `[PAUSE]` 标出**一处真实存在的停顿**。')
    lines.append('你的任务：判断这处停顿在**语义结构**上属于哪一类。\n')
    lines.append('**注意：不要猜停顿有多长。** 我们刻意没给时长——给了就会锚定。')
    lines.append('你只判结构，时长由我们事后按类别统计。\n')
    lines.append('## 标注档位\n')
    lines.append('| kind | 判据 |')
    lines.append('|---|---|')
    lines.append('| `drop` | **完全不停也不影响理解。** 四种情况：'
                 '<br>① 语法性逗号（`like` `as` `than` `that` 前后是同一语法单元）'
                 '<br>② 填充词/呼语后紧接主句（`Well` `Now` `And` `Oh`）'
                 '<br>③ 反意疑问结构内部的插入成分（`..., then, shouldn\'t he?` 里的 then）'
                 '<br>④ 连续短项列举 |')
    lines.append('| `tight` | **只停半拍（0.15~0.25s），且停顿后这句话还没说完。**'
                 '<br>① 插入语/补充说明（`he was twenty,` 后面接主句）'
                 '<br>② 从句没说完，后面还有主句成分'
                 '<br>③ 修饰语与中心词之间（`a memory [PAUSE] of a boy`）'
                 '<br>**⚠ 句末不能用 tight。** 后面接新句子就必须是 clause 以上 |')
    lines.append('| `clause` | **正常分句边界（0.4~0.6s）。这是句末的默认值。**'
                 '<br>① 两个完整分句之间（各有主谓）'
                 '<br>② 并列/转折/定语从句连词之前（but / and / so / because / which） |')
    lines.append('| `beat` | **情绪/信息落点（0.6~0.8s）。三条必须同时满足：**'
                 '<br>① 停顿前那一段是完整、有分量的话（不是从句、不是半句）'
                 '<br>② 停顿后接的是回应/结论/新信息，不是继续同一句'
                 '<br>③ **把停顿缩到 0.2s，这句话的力度会明显损失**'
                 '<br>（第③条是硬标准：如果你觉得缩短了也没差，那就不是 beat） |')
    lines.append('| `paragraph` | **段落级（≥1.5s）。**'
                 '<br>① 话题/场景切换　② 时间或地点跳转　③ 视角转换（叙述→内心独白） |')
    lines.append('\n**判定顺序（不许反，每条按顺序问一遍）：**\n')
    lines.append('1. **完全不停会不会听不懂？** 不会 → `drop`')
    lines.append('2. **停顿后这句话说完了吗？** 没说完 → `tight`')
    lines.append('3. **是不是换话题/换场景/换视角？** 是 → `paragraph`')
    lines.append('4. **beat 的三条硬判据都满足吗？** 满足 → `beat`')
    lines.append('5. 剩下全是 `clause`\n')
    lines.append('> 上一轮 16 条对白的三方标注 Kappa 只有 0.61，分歧全在 tight 和 beat 上：')
    lines.append('> 有人把句末判 tight、有人把句末一律判 clause。')
    lines.append('> 所以这一版把「句末不能用 tight」「句末默认 clause」写死了。\n')
    lines.append('## 反例（容易标错）\n')
    lines.append('- `as we begin our story [PAUSE] which just might rekindle` → `clause`。'
                 '`which` 引导定语从句，是分句边界。')
    lines.append('- `that memory [PAUSE] of a boy` → `tight`。`of a boy` 是修饰语，'
                 '和中心词 `memory` 不能断开。')
    lines.append('- `He was twenty [PAUSE] and he was in the war` → `clause`。并列连词前。')
    lines.append('- `Well [PAUSE] it was in somebody\'s house` → `drop`。填充词黏在主句上。')
    lines.append('- `...a full sentence. [PAUSE] Then a new thought begins` → `clause`（默认），'
                 '**不是** tight —— 句末不能用 tight。')
    lines.append('- 若上一条你判断「缩到 0.2s 会明显损失力度」，才升为 `beat`。\n')
    lines.append('## 输出格式\n')
    lines.append('纯 JSON（不要 markdown 代码块、不要注释），写到指定路径：\n')
    lines.append('```json')
    lines.append('{')
    lines.append('  "P001": {"kind": "clause", "why": "which 引导定语从句"},')
    lines.append('  "P002": {"kind": "drop", "why": "填充词后紧接主句"}')
    lines.append('}')
    lines.append('```\n')
    lines.append('`why` 用中文，不超过 20 字，必须写出你依据的是哪个词/哪个结构。\n')
    lines.append('## 待标样本（%d 条）\n' % len(samples))
    for s in samples:
        lines.append('**%s**  %s\n' % (s['key'], s['text']))
    open(OUT_T, 'w', encoding='utf-8').write('\n'.join(lines))
    print('写出任务书 → %s' % OUT_T)

    # 事后核对用的时长分布（不外露）
    print('\n（仅供事后核对，不要给标注者）各层实际条数:')
    gs = [s['_gap'] for s in samples]
    print('  gap p10 %.2f p50 %.2f p90 %.2f' % (
        np.percentile(gs, 10), np.median(gs), np.percentile(gs, 90)))


if __name__ == '__main__':
    main()
