# -*- coding: utf-8 -*-
'''_ann_dlg_diag.py -- 看对白轨分歧到底集中在哪种槽位上。'''
import collections
import glob
import json
import os

ROOT = 'G:/_setup'
T = os.path.join(ROOT, '_ann')


def main():
    task = json.load(open(os.path.join(T, 'tasks_tier_full', 'batch_0037.json'), encoding='utf-8'))
    slots = {}
    for it in task['items']:
        for s in it['slots']:
            slots[s['bid']] = {'right': (s.get('right') or '').strip(),
                               'punct': s.get('punct'), 'sid': it['sid']}

    D = {}
    for n in ('ds', 'hy4'):
        fp = os.path.join(T, 'out_v2_dlg', n, 'batch_0037.json')
        D[n] = {x['sid']: x for x in json.load(open(fp, encoding='utf-8'))['items']}

    # 每个 bid 的票
    v = {}
    for n in D:
        for sid, it in D[n].items():
            for p in (it.get('pause') or []):
                if p.get('bid') in slots:
                    v.setdefault(p['bid'], {})[n] = str(p.get('tier')).lower()

    empty = [b for b in slots if not slots[b]['right']]
    print('槽位 %d，右段为空（句末/引语末） %d (%.0f%%)'
          % (len(slots), len(empty), 100.0 * len(empty) / len(slots)))

    def bucket(b):
        if not slots[b]['right']:
            return 'empty'
        return 'txt'

    ag = collections.Counter()
    tot = collections.Counter()
    for b, d in v.items():
        if len(d) < 2:
            continue
        k = bucket(b)
        tot[k] += 1
        if len(set(d.values())) == 1:
            ag[k] += 1
    for k in tot:
        print('  %-6s 槽 %-3d 一致 %-3d (%.0f%%)' % (k, tot[k], ag[k], 100.0 * ag[k] / tot[k]))

    print('')
    print('右段为空时的档位选择（各模型）：')
    for n in D:
        c = collections.Counter(v[b][n] for b in empty if n in v.get(b, {}))
        print('  %-4s %s' % (n, dict(c)))

    print('')
    print('分歧且右段为空的槽（应全部判句末收束）：')
    for b in empty:
        d = v.get(b, {})
        if len(d) >= 2 and len(set(d.values())) > 1:
            print('   %-14s %s' % (b, d))


if __name__ == '__main__':
    main()
