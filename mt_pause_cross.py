# -*- coding: utf-8 -*-
"""语言直觉 × 声学实测 的 2×2 交叉：哪些该停没停，哪些不该停却停了。

两个方向的问题必须分开算
  该停没停   → 句子黏在一起，听不出结构
  不该停却停 → **比前者更伤**：一句台词被切成两句
               例：L069 `some money [0.50s] then shouldn't he?`
               而 L008/L014/L068 的反意疑问被 0.24~0.36s 硬切开

判定来源
  intent  pause_intent.json（LLM 语义判定：must / opt / no）
  gap     _punct_expr.json（声学实测）

判据
  漏停     intent=must 且 gap < 0.10
  偏短     intent=must 且 0.10 ≤ gap < 0.20
  多余     intent=no   且 gap > 0.15
  正常     其余

用法
  python -u mt_pause_cross.py
"""
import argparse
import json
import os
import sys

sys.path.insert(0, r'G:/_setup')

MUST_MIN = 0.10
MUST_OK = 0.20
NO_MAX = 0.15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--intent', default=r'G:/_setup/pause_intent.json')
    ap.add_argument('--expr', default=r'G:/_setup/_punct_expr.json')
    ap.add_argument('--out', default=r'G:/_setup/_pause_cross.json')
    a = ap.parse_args()

    intent = json.load(open(a.intent, encoding='utf-8'))
    expr = json.load(open(a.expr, encoding='utf-8'))

    rows = []
    for k, per in intent.items():
        if k.startswith('_'):
            continue
        er = {r['i']: r for r in expr.get(k, []) if r.get('status') != 'unaligned'}
        for si, it in per.items():
            i = int(si)
            r = er.get(i)
            if not r:
                rows.append(dict(key=k, i=i, intent=it, status='no_measure'))
                continue
            gap = r['gap']
            if it == 'must':
                v = 'missing' if gap < MUST_MIN else ('short' if gap < MUST_OK else 'ok')
            elif it == 'no':
                v = 'extra' if gap > NO_MAX else 'ok'
            else:
                v = 'ok' if gap <= 0.40 else 'long'
            rows.append(dict(key=k, i=i, word=r['word'] + r['punct'], intent=it,
                             gap=gap, pre_ratio=r['pre_ratio'], f0_st=r['f0_st'],
                             acou=r['status'], verdict=v))

    def show(title, v, note=''):
        sub = [r for r in rows if r['verdict'] == v]
        sub.sort(key=lambda r: -r.get('gap', 0) if v in ('extra', 'long') else r.get('gap', 0))
        print('\n%s %d 处%s' % (title, len(sub), ('  ' + note) if note else ''))
        for r in sub:
            print('  %-5s %-14s %s  gap %.3fs  延长 %.2fx  F0 %s'
                  % (r['key'], r['word'], r['acou'], r['gap'], r['pre_ratio'],
                     ('%+.1f' % r['f0_st']) if r['f0_st'] is not None else 'n/a'))
        return sub

    print('===== 语言直觉 × 声学实测 =====')
    n = len([r for r in rows if r['verdict'] != 'no_measure'])
    cnt = {}
    for r in rows:
        cnt[r['verdict']] = cnt.get(r['verdict'], 0) + 1
    print('可测 %d 处：' % n + '  '.join('%s=%d' % (k, cnt.get(k, 0))
                                       for k in ('ok', 'missing', 'short', 'extra', 'long')))

    miss = show('【该停没停】', 'missing', '句子会黏在一起')
    short = show('【该停但偏短】', 'short', '0.10~0.20s，可补')
    extra = show('【不该停却停了】', 'extra', '**比漏停更伤，一句被切成两句**')
    long_ = show('【可停档但停长了】', 'long', '>0.40s')

    json.dump(rows, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n===== 要做的事 =====')
    if miss or short:
        print('  补停（生成后检测不通过则重生成，最后才靠后期）：%s'
              % ' '.join('%s/%s' % (r['key'], r['word']) for r in miss + short))
    if extra:
        print('  压缩多余停顿（删静音，不是插静音）：%s'
              % ' '.join('%s/%s(%.2fs)' % (r['key'], r['word'], r['gap']) for r in extra))
    if long_:
        print('  可停档偏长，可选择性压缩：%s'
              % ' '.join('%s/%s(%.2fs)' % (r['key'], r['word'], r['gap']) for r in long_))
    print('  报告: %s' % a.out)


if __name__ == '__main__':
    main()
