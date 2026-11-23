# -*- coding: utf-8 -*-
"""build_word_template.py —— 从 Wonder 真实录音的词级韵律特征中提取"词位模板"。

产出 word_template.json：
  - word_first      句首词 5 点轮廓（相对句内中位，半音）
  - word_mid_q1/q2/q3  句中词按相对位置三等分桶
  - word_last       句末词（.!?）
  - word_comma      逗号词
  - global_mean     全词均值（叠加时去均值，保留生成端自身起伏）
每个值: {"st": [5 点], "n": 样本数}

用法: python -u build_word_template.py
"""
import json
import sys

import numpy as np

sys.path.insert(0, 'G:/_setup')
import prosody_model_a as M  # noqa: E402

OUT = M.ROOT / 'word_template.json'


def mean_prof(rows):
    P = np.array([w['target'][:5] for w in rows if w['voiced']])
    if len(P) < 8:
        return None
    return [round(float(x), 3) for x in P.mean(0)], int(len(P))


def main():
    recs = json.loads((M.ROOT / 'features.json').read_text(encoding='utf-8'))
    first, mid, last, comma = [], [], [], []
    mids = {1: [], 2: [], 3: []}
    for r in recs:
        ws = r['words']
        n = len(ws)
        for i, w in enumerate(ws):
            tail = w['word'][-1:]
            if i == 0:
                first.append(w)
            elif i == n - 1:
                if tail in '.!?':
                    last.append(w)
                elif tail == ',':
                    comma.append(w)
                else:
                    mid.append(w)
            else:
                mid.append(w)
                if tail == ',':
                    comma.append(w)
        # 句中词的相对位置三等分
        inner = [w for w in ws[1:n - 1] if w['voiced']]
        for j, w in enumerate(inner):
            q = 1 + min(2, int(3 * j / max(1, len(inner))))
            mids[q].append(w)

    allp = np.array([w['target'][:5] for r in recs for w in r['words'] if w['voiced']])
    template = dict(global_mean=round(float(allp.mean()), 3), n_words=int(len(allp)))
    for key, rows in [('word_first', first), ('word_mid', mid), ('word_last', last), ('word_comma', comma)]:
        r = mean_prof(rows)
        if r:
            template[key] = dict(st=r[0], n=r[1])
    for q, rows in mids.items():
        r = mean_prof(rows)
        if r:
            template['mid_q%d' % q] = dict(st=r[0], n=r[1])

    OUT.write_text(json.dumps(template, ensure_ascii=False, indent=1), encoding='utf-8')
    for k, v in template.items():
        if k == 'global_mean':
            print('global_mean = %+.3f  (n=%d)' % (v, template['n_words']))
        elif k == 'n_words':
            continue
        else:
            print('%-11s n=%4d  %s  | 首尾差 %+.2f（去均值后 %+.2f）'
                  % (k, v['n'], ' '.join('%+.2f' % x for x in v['st']),
                     v['st'][-1] - v['st'][0],
                     (v['st'][-1] - template['global_mean']) - (v['st'][0] - template['global_mean'])))
    print('写出', OUT)


if __name__ == '__main__':
    main()
