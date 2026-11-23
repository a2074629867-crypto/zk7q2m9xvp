# -*- coding: utf-8 -*-
'''_ann_check_one.py -- 单个执行体自查自己的产出（铺量时每路自己跑）。

比 _ann_verify.py 更严：连 rate 对象格式、stress 下标、why 缺失都判 BAD。
用法：python _ann_check_one.py --dir _ann/out_full/narr/hy4 --batches batch_0001 batch_0002
'''
import argparse
import json
import os
import sys

ROOT = 'G:/_setup'
TASKS = os.path.join(ROOT, '_ann', 'tasks_tier_full')   # 可被 --tasks 覆盖（情境化包在 tasks_ctx）
NARR_T = {'short', 'mid', 'long'}
DLG_T = {'zero', 'short', 'mid', 'long'}


def check_one(d, bname, tasks=None):
    tp = os.path.join(d, bname)
    sp = os.path.join(tasks or TASKS, bname)
    if not os.path.exists(sp):
        return ['任务包不存在: ' + sp], 0
    src = json.load(open(sp, encoding='utf-8'))
    # ★ 情境化包（tasks_ctx）没有 track 字段，mode=tier_ctx；对白档位含 zero。
    trk = src.get('track') or ('dlg' if 'ctx' in str(src.get('mode') or '') else 'narr')
    ok_set = NARR_T if trk == 'narr' else DLG_T
    if not os.path.exists(tp):
        return ['没写文件: ' + tp], 0
    try:
        obj = json.load(open(tp, encoding='utf-8'))
    except Exception as e:
        return ['JSON 解析失败: %s' % str(e)[:100]], 0
    items = obj.get('items') if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return ['顶层不是 {"items":[...]}'], 0

    got = {}
    dup = []
    for it in items:
        s = it.get('sid')
        if not s:
            continue
        if s in got:
            dup.append(s)
        got[s] = it

    errs = []
    if dup:
        errs.append('sid 重复 %d: %s' % (len(dup), dup[:5]))

    nslot = 0
    for it in src['items']:
        sid = it['sid']
        r = got.get(sid)
        if not r:
            errs.append('缺 sid %s' % sid)
            continue
        want = [s['bid'] for s in it['slots']]
        have = [p.get('bid') for p in (r.get('pause') or [])]
        miss = [b for b in want if b not in have]
        extra = [b for b in have if b and b not in want]
        if miss:
            errs.append('%s 缺 bid %s' % (sid, miss[:4]))
        if extra:
            errs.append('%s 多 bid %s' % (sid, extra[:4]))
        for p in (r.get('pause') or []):
            nslot += 1
            t = str(p.get('tier') or '').strip().lower()
            if t not in ok_set:
                errs.append('%s 档位越轨 %r' % (p.get('bid'), t))
            if not str(p.get('why') or '').strip():
                errs.append('%s 缺 why' % p.get('bid'))
        rt = r.get('rate')
        if rt is not None:
            if not isinstance(rt, dict):
                errs.append('%s rate 不是对象(%r) —— 必须是 {"rate":0.78,"why":"..."}' % (sid, rt))
            elif not isinstance(rt.get('rate'), (int, float)):
                errs.append('%s rate 非数值' % sid)
            elif not (0.72 <= float(rt['rate']) <= 0.84):
                errs.append('%s rate 越界 %s' % (sid, rt['rate']))
        sts = r.get('stress') or []
        ntok = len(it.get('tokens') or [])
        if len(sts) > 3:
            errs.append('%s stress %d 个（超 3）' % (sid, len(sts)))
        for s in sts:
            if not isinstance(s.get('tok'), int) or not (0 <= s['tok'] < ntok):
                errs.append('%s stress tok=%r 超界' % (sid, s.get('tok')))
            if s.get('level') not in (1, 2, 3):
                errs.append('%s stress level=%r' % (sid, s.get('level')))
    return errs, nslot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--batches', nargs='+', required=True)
    ap.add_argument('--tasks', default=None,
                    help='任务包目录，默认 _ann/tasks_tier_full；情境化包用 _ann/tasks_ctx')
    a = ap.parse_args()
    bad = 0
    for b in a.batches:
        if not b.endswith('.json'):
            b += '.json'
        errs, n = check_one(a.dir, b, a.tasks)
        if errs:
            bad += 1
            print('[BAD] %s  %d 个问题' % (b, len(errs)))
            for e in errs[:8]:
                print('   -', e)
        else:
            print('[OK ] %s  %d 槽位' % (b, n))
    print('')
    print('全部通过' if not bad else '有 %d 批未通过，修完再跑一次' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
