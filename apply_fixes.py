# -*- coding: utf-8 -*-
"""
把审阅后的修正应用到 Parakeet blocks 标注，并合并被切碎的切片。

修正来源：用户人工审阅 + small.en 交叉核对（每条都有佐证）。
切片合并：sleeps 的词时间戳 1593.03-1593.91 跨过切片边界 1593.11 => 该词被切成两半。

输出：wonder_v5full_df3_final.list / wonder_final.json
"""
import json
import os
import re
import subprocess

import numpy as np
import soundfile as sf

SR = 32000
D = 'G:/GPT-SoVITS/_dataset_v5full'
DF3 = 'G:/_setup/_denoise_full/wonder_train_df3.wav'
SLICED = D + '/sliced_df3'
OUT_PREFIX = D + '/wonder_v5full_df3_final'

# ---- 1) 切片合并：(A_t0, A_t1, B_t1) -> 合并成 A_t0..B_t1 ----
MERGES = [
    (1590.19, 1593.11, 1594.30),   # ...soundest of | sleeps.  => sleeps 被切两半
]

# ---- 2) 文本修正：按片 t0 定位，(旧, 新) ----
FIXES = [
    (1590.19, 'So he drifts off to the soundest of', 'Zoe drifted off to the soundest of'),
    (1465.30, 'sleep. So he closed her eyes and', 'sleep. Zoe closed her eyes and'),
    (60.46, 'Purple thumbtags', 'Purple thumbtacks'),
    (1246.41, 'Think of the thousand of languages being', 'Think of the thousands of languages being'),
    (360.66, 'so explained that sometimes her mind', 'Zoe explained that sometimes her mind'),
    (50.92, 'Stock of prize possessions sat', 'A stock of prized possessions sat'),
    (408.26, 'Grandma said, staring off the stars.', 'Grandpa said, staring off at the stars.'),
    (358.09, 'their eyes wandered the constellations,', 'As their eyes wandered the constellations,'),
]


def fix_words(words, old, new):
    """按词序列匹配替换（保持时间戳）"""
    ot = old.split()
    nt = new.split()
    out = []
    i = 0
    while i < len(words):
        if i + len(ot) <= len(words):
            seg = [words[i + k][2] for k in range(len(ot))]
            if [t.lower() for t in seg] == [t.lower() for t in ot]:
                a = words[i][0]
                b = words[i + len(ot) - 1][1]
                for k, w in enumerate(nt):
                    out.append([a, b, w])
                i += len(ot)
                continue
        out.append(words[i])
        i += 1
    return out


def main():
    L = json.load(open(D + '/wonder_blocks.json', encoding='utf-8'))['slices']
    print('原始 %d 片' % len(L))

    # ---- 合并切片 ----
    x = sf.read(DF3, dtype='float32', always_2d=True)[0].mean(1)
    for a_t0, a_t1, b_t1 in MERGES:
        fa = 'wonder_train_df3.wav_%010d_%010d.wav' % (int(a_t0 * SR), int(a_t1 * SR))
        fb = 'wonder_train_df3.wav_%010d_%010d.wav' % (int(a_t1 * SR), int(b_t1 * SR))
        fn = 'wonder_train_df3.wav_%010d_%010d.wav' % (int(a_t0 * SR), int(b_t1 * SR))
        seg = x[int(a_t0 * SR):int(b_t1 * SR)]
        sf.write(os.path.join(SLICED, fn), seg, SR, subtype='PCM_16')
        for f in (fa, fb):
            p = os.path.join(SLICED, f)
            if os.path.exists(p):
                os.remove(p)
        print('合并切片 %.2f-%.2f (%.2fs)  %s' % (a_t0, b_t1, b_t1 - a_t0, fn))
        # 更新 json：A 片扩到 b_t1 并把 B 片的词并进来，然后删掉 B 片
        ia = next(i for i, s in enumerate(L) if abs(s['t0'] - a_t0) < 0.02)
        ib = next(i for i, s in enumerate(L) if abs(s['t0'] - a_t1) < 0.02)
        L[ia]['file'] = fn
        L[ia]['t1'] = b_t1
        na, nb = len(L[ia]['words']), len(L[ib]['words'])
        L[ia]['words'] = sorted(L[ia]['words'] + L[ib]['words'], key=lambda w: w[0])
        L[ia]['text'] = ' '.join(w for _, _, w in L[ia]['words'])
        L = [s for i, s in enumerate(L) if i != ib]
        print('  A 片 %d 词 + B 片 %d 词 -> %d 词 | %s'
              % (na, nb, len(L[ia]['words']), L[ia]['text']))
    print('合并后 %d 片' % len(L))

    # ---- 文本修正 ----
    nfix = 0
    for t0, old, new in FIXES:
        idx = next((i for i, s in enumerate(L) if abs(s['t0'] - t0) < 0.05), None)
        if idx is None:
            print('  !! 找不到片 %.2f (%s)' % (t0, old[:30]))
            continue
        s = L[idx]
        if old not in s['text']:
            print('  !! 文本不匹配 [%.2f]: 期望 %r / 实际 %r' % (t0, old[:40], s['text'][:40]))
            continue
        s['text'] = s['text'].replace(old, new)
        s['words'] = fix_words(s['words'], old, new)
        nfix += 1
        print('  修正 [%.2f] %s' % (t0, new[:60]))
    print('应用 %d/%d 处修正' % (nfix, len(FIXES)))

    # ---- 输出 ----
    n_words = sum(len(s['words']) for s in L)
    json.dump(dict(slices=L, n_words=n_words),
              open(D + '/wonder_final.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with open(OUT_PREFIX + '.list', 'w', encoding='utf-8') as f:
        for s in L:
            if not s['words']:
                continue
            p = os.path.join(SLICED, s['file']).replace('\\', '/')
            f.write('%s|Calm|en|%s\n' % (p, s['text']))
    n_empty = sum(1 for s in L if not s['words'])
    print('\n写出 %s.list  (%d 行 / %d 词 / 空片 %d)' % (OUT_PREFIX, len(L) - n_empty, n_words, n_empty))


if __name__ == '__main__':
    main()
