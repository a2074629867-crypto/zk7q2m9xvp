# -*- coding: utf-8 -*-
"""v5full_normalize.py —— 标注文本规范化 + 生成审阅用 JSON

规范化规则（都基于实测的 GSV 文本前端行为）：
  1) 去掉单/双引号 —— 实测 `'...'` 会被前端变成 `-`（一个停顿符号），
     与原有的逗号叠加会多出一个停顿；而撇号（Zoe's / weren't）必须保留。
     规则：只删「不与字母相邻」的撇号，以及所有双引号。
  2) 修连字符被空格切开：`seven -year -old's` → `seven-year-old's`
  3) 折叠多余空白
  4) 数字保留（实测前端自动转词：16→sixteen、187→one hundred eighty-seven）

同时为每条切片计算：
  - 首/尾静音时长（能量法，-35dB 相对峰值）
  - 尾部静音是否与结尾标点匹配（用于审阅页高亮）
"""
import os
import re
import json
import glob

import numpy as np
import soundfile as sf

D = 'G:/GPT-SoVITS/_dataset_v5full'
RAW_LIST = D + '/wonder_v5full.list'
OUT_LIST = D + '/wonder_v5full_norm.list'
OUT_JSON = D + '/review_labels.json'
SR = 32000


def norm_text(t):
    s = t
    # 连字符被空格切开：'seven -year' → 'seven-year'；'re -inspect' → 're-inspect'
    s = re.sub(r'(\w)\s+-\s*(\w)', r'\1-\2', s)
    # 撇号：仅保留「前是字母 且 后是字母」的（Zoe's / weren't / old's）
    s = re.sub(r"(?<![A-Za-z])'", '', s)
    s = re.sub(r"'(?![A-Za-z])", '', s)
    # 双引号全去
    s = s.replace('"', '').replace('\u201c', '').replace('\u201d', '')
    # 折叠空白；标点前不留空格
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+([.,?!;:])', r'\1', s)
    return s


def edge_silence(path, thr_db=-35.0, min_sil=0.05):
    x, sr = sf.read(path, dtype='float64', always_2d=True)
    x = x.mean(1)
    if len(x) == 0:
        return 0.0, 0.0, 0.0
    fl = int(0.025 * sr)
    hop = int(0.010 * sr)
    m = max(1, (len(x) - fl) // hop + 1)
    idx = np.arange(fl)[None, :] + hop * np.arange(m)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    r = np.sqrt((x[idx] ** 2).mean(1) + 1e-20)
    rdb = 20 * np.log10(r + 1e-12)
    v = rdb > (rdb.max() + thr_db)
    lead = 0
    while lead < m and not v[lead]:
        lead += 1
    trail = 0
    while trail < m and not v[m - 1 - trail]:
        trail += 1
    return lead * hop / sr, trail * hop / sr, len(x) / sr


def main():
    rows = []
    for line in open(RAW_LIST, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line.strip():
            continue
        p = line.split('|')
        if len(p) >= 4:
            rows.append({'path': p[0], 'spk': p[1], 'lang': p[2], 'raw': p[3]})

    print('读入 %d 条' % len(rows))

    out_lines = []
    review = []
    n_changed = 0
    for i, r in enumerate(rows):
        t = norm_text(r['raw'])
        if t != r['raw']:
            n_changed += 1
        base = os.path.basename(r['path'])
        m = re.search(r'_(\d{10})_(\d{10})\.wav$', base)
        t0 = int(m.group(1)) / SR if m else 0.0
        t1 = int(m.group(2)) / SR if m else 0.0
        p = r['path'].replace('\\', '/')
        lead, trail, dur = (0.0, 0.0, t1 - t0)
        if os.path.exists(p):
            lead, trail, dur = edge_silence(p)
        nw = len(t.split())
        wps = nw / max(dur, 1e-6)
        # 一致性：结尾是句号级标点但尾部静音很短 / 结尾无标点但尾部静音很长
        warn = ''
        end_punct = t[-1] if t and t[-1] in '.?!,;:' else ''
        if end_punct in '.?!' and trail < 0.25:
            warn = 'end_period_but_short_trail'
        elif not end_punct and trail > 1.2:
            warn = 'long_trail_no_punct'
        elif nw < 3:
            warn = 'short_text'
        out_lines.append('%s|%s|%s|%s' % (r['path'], r['spk'], r['lang'], t))
        review.append({'i': i, 'file': base, 't0': round(t0, 2), 't1': round(t1, 2),
                       'dur': round(dur, 2), 'nwords': nw, 'wps': round(wps, 2),
                       'lead': round(lead, 2), 'trail': round(trail, 2),
                       'raw': r['raw'], 'text': t, 'warn': warn,
                       'changed': t != r['raw']})

    open(OUT_LIST, 'w', encoding='utf-8').write('\n'.join(out_lines) + '\n')
    json.dump({'n': len(review), 'slices': review},
              open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('文本被改动的 %d 条' % n_changed)
    print('写出 %s (%d 条)' % (OUT_LIST, len(out_lines)))
    print('写出 %s' % OUT_JSON)
    from collections import Counter
    c = Counter(r['warn'] or '(ok)' for r in review)
    print('\n审阅标记分布:')
    for k, v in c.most_common():
        print('   %-28s %d' % (k, v))
    print('\n改动样例:')
    for r in review:
        if r['changed']:
            print('   原: %s' % r['raw'][:80])
            print('   新: %s' % r['text'][:80])
    print('\n首/尾静音分布:')
    lead = np.array([r['lead'] for r in review])
    trail = np.array([r['trail'] for r in review])
    for nm, a in (('lead', lead), ('trail', trail)):
        print('   %s 中位 %.2fs  p90 %.2fs  最长 %.2fs' % (nm, np.median(a), np.percentile(a, 90), a.max()))


if __name__ == '__main__':
    main()
