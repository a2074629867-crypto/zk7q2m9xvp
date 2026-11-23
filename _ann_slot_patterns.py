# -*- coding: utf-8 -*-
'''_ann_slot_patterns.py -- 统计 1646 个停顿槽位的真实结构模式。

目的：看 short/mid 的判别能不能从「靠模型感觉」变成「按模式查表」。
不写任何产物，只打印。
'''
import collections
import json
import os

ROOT = 'G:/_setup'
TASKS = os.path.join(ROOT, '_ann', 'tasks_tier_full')

# 典型连接词 / 关系词
SUBORD = {'when', 'while', 'as', 'if', 'though', 'although', 'because', 'till',
          'until', 'since', 'before', 'after', 'unless', 'whether', 'where',
          'than', 'so'}
COORD = {'and', 'but', 'or', 'nor', 'yet', 'for'}
REL = {'which', 'who', 'whom', 'whose', 'that', 'where'}


def firstword(s):
    s = (s or '').strip()
    return s.split()[0].lower().strip(',.;:') if s.split() else ''


def lastword(s):
    s = (s or '').strip()
    return s.split()[-1].lower().strip(',.;:') if s.split() else ''


def main():
    idx = json.load(open(os.path.join(TASKS, 'INDEX.json'), encoding='utf-8'))
    per_track = collections.Counter()
    punct = collections.defaultdict(collections.Counter)
    right_head = collections.defaultdict(collections.Counter)
    shapes = collections.defaultdict(collections.Counter)

    for e in idx:
        d = json.load(open(os.path.join(TASKS, e['file']), encoding='utf-8'))
        trk = d.get('track', 'narr')
        for it in d['items']:
            for s in it['slots']:
                per_track[trk] += 1
                punct[trk][(s.get('punct') or '?')] += 1
                fw = firstword(s.get('right'))
                right_head[trk][fw] += 1
                if fw in COORD:
                    kind = 'coord:' + fw
                elif fw in SUBORD:
                    kind = 'subord:' + fw
                elif fw in REL:
                    kind = 'rel:' + fw
                elif fw in ('', 'i', 'he', 'she', 'it', 'they', 'we', 'you'):
                    kind = 'newclause'
                else:
                    kind = 'other:' + fw
                shapes[trk][kind] += 1

    print('=== 槽位总数 ===', dict(per_track))
    for trk in ('narr', 'dlg'):
        tot = per_track[trk] or 1
        print('')
        print('[%s] n=%d' % (trk, tot))
        print('  标点:', dict(punct[trk].most_common(8)))
        print('  右首词 top15:', dict(right_head[trk].most_common(15)))
        print('  粗略模式 top18:')
        for k, v in shapes[trk].most_common(18):
            print('    %-16s %5d  %5.1f%%' % (k, v, 100.0 * v / tot))
        cov = sum(v for k, v in shapes[trk].items() if not k.startswith('other:'))
        print('  非 other 覆盖: %.1f%%' % (100.0 * cov / tot))
        nor = sum(v for k, v in shapes[trk].items() if k.startswith('other:'))
        print('  other 尾长:', len([k for k in shapes[trk] if k.startswith('other:')]), '种 / 共', nor, '槽')


if __name__ == '__main__':
    main()
