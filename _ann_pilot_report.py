# -*- coding: utf-8 -*-
'''_ann_pilot_report.py -- 看几路模型在同一批上的重叠度（判断能不能上三票投票）。

只读，不写产物。用法：python _ann_pilot_report.py batch_0001 ds hy4
'''
import json
import os
import sys

ROOT = 'G:/_setup'
ORD = {'zero': 0, 'short': 1, 'mid': 2, 'long': 3}
# 产物根目录可换（ANN_OUT=out_v2_narr 这种），默认老目录
OUT = os.environ.get('ANN_OUT', 'out_tier_full')


def rate_of(rec):
    """容忍两种写法：{"rate":0.78,"why":...} 与裸数字 0.78（后者不合规但要能统计）。"""
    r = (rec or {}).get('rate')
    if isinstance(r, dict):
        return r.get('rate')
    if isinstance(r, (int, float)):
        return float(r)
    return None


def main():
    bn = sys.argv[1] if len(sys.argv) > 1 else 'batch_0001'
    names = sys.argv[2:] or ['ds', 'hy4']
    tp = os.path.join(ROOT, '_ann', 'tasks_tier_full', bn + '.json')
    task = json.load(open(tp, encoding='utf-8'))
    items = {it['sid']: it for it in task['items']}
    print('batch=%s track=%s items=%d' % (bn, task.get('track'), len(items)))

    D = {}
    for n in names:
        fp = os.path.join(ROOT, '_ann', OUT, n, bn + '.json')
        if not os.path.exists(fp):
            print('  [缺] %s' % n)
            continue
        D[n] = {x['sid']: x for x in json.load(open(fp, encoding='utf-8'))['items']}
    names = list(D)
    print('可比较的模型: %s' % names)

    # ---- pause ----
    tot = 0
    cnt = {k: 0 for k in range(len(names) + 1)}
    diffs = []
    for sid, it in items.items():
        m = {n: {p['bid']: p['tier'] for p in (D[n].get(sid, {}).get('pause') or [])} for n in names}
        for s in it['slots']:
            vals = [m[n].get(s['bid']) for n in names]
            if any(v is None for v in vals):
                continue
            tot += 1
            if len(set(vals)) == 1:
                cnt[len(vals)] += 1
            else:
                diffs.append((s['bid'], vals,
                              s['left'][-20:] + ' || ' + s['right'][:20]))
    print('')
    print('-- pause 逐槽 --')
    print('  可比槽位 %d，全员一致 %d (%.0f%%)，分歧 %d'
          % (tot, cnt[len(names)], 100.0 * cnt[len(names)] / max(1, tot), len(diffs)))
    if len(names) == 2 and tot:
        adj = 0
        for d in diffs:
            a, b = d[1]
            if abs(ORD.get(a, 9) - ORD.get(b, 9)) <= 1:
                adj += 1
        print('  其中邻档差异 %d (占分歧 %.0f%%)' % (adj, 100.0 * adj / max(1, len(diffs))))
    for d in diffs[:10]:
        print('   %-14s %s | %s' % (d[0], d[1], d[2]))

    # ---- rate ----
    print('')
    print('-- rate --')
    for n in names:
        vals = [rate_of(D[n][sid]) for sid in items if sid in D[n]]
        nn = [v for v in vals if v]
        print('  %-4s 句数=%d 放慢=%d null=%d 均值=%s'
              % (n, len(vals), len(nn), len(vals) - len(nn),
                 round(sum(nn) / len(nn), 3) if nn else '-'))
    if len(names) == 2:
        pairs = [(rate_of(D[names[0]].get(s)), rate_of(D[names[1]].get(s))) for s in items]
        both = [(x, y) for x, y in pairs if x and y]
        one = [(x, y) for x, y in pairs if bool(x) != bool(y)]
        print('  两边都给值 %d 条，均值绝对差 %s'
              % (len(both), round(sum(abs(x - y) for x, y in both) / len(both), 4) if both else '-'))
        print('  一边给一边 null %d 条' % len(one))

    # ---- stress ----
    print('')
    print('-- stress --')
    for n in names:
        c = sum(len(D[n][s].get('stress') or []) for s in items if s in D[n])
        print('  %-4s 个数=%d' % (n, c))
    if len(names) == 2:
        inter = union = 0
        for s in items:
            a = {x['tok'] for x in (D[names[0]].get(s, {}).get('stress') or [])}
            b = {x['tok'] for x in (D[names[1]].get(s, {}).get('stress') or [])}
            inter += len(a & b)
            union += len(a | b)
        print('  重读位置 Jaccard %s' % (round(inter / union, 3) if union else '-'))


if __name__ == '__main__':
    main()
