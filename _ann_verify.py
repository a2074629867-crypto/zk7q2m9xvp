# -*- coding: utf-8 -*-
'''_ann_verify.py -- 核三路子 Agent 的标注产物是否真的逐处标了（防偷懒/防漏标）。

看四件事：
  1. sid 覆盖：任务包里每个 sid 都必须出现
  2. bid 覆盖：pause 的 bid 必须 == slots 的 bid 集合（漏/多都算错）
  3. 档位分布：单一档 >90% 判退化，要重跑
  4. 越轨档位：旁白出现 zero/drop 就是混了尺子

用法：python _ann_verify.py --dirs _ann/out_tier_full/hy4 ...
'''
import argparse
import collections
import glob
import json
import os
import sys

NARR_T = {'short', 'mid', 'long'}
DLG_T = {'zero', 'short', 'mid', 'long'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dirs', nargs='+', required=True)
    ap.add_argument('--tasks', default='_ann/tasks_tier_full')
    a = ap.parse_args()

    # 只校「这几路实际跑过的 batch」，否则照 48 批全量比会把没跑的批当缺 sid
    covered = set()
    for d in a.dirs:
        for fp in glob.glob(os.path.join(d, 'batch_*.json')):
            covered.add(os.path.basename(fp))

    idx = json.load(open(os.path.join(a.tasks, 'INDEX.json'), encoding='utf-8'))
    tasks = {}
    for e in idx:
        if e['file'] not in covered:
            continue
        p = os.path.join(a.tasks, e['file'])
        tasks[e['file']] = json.load(open(p, encoding='utf-8'))

    bad_any = False
    for d in a.dirs:
        name = os.path.basename(d.rstrip('/' + chr(92)))
        files = sorted(glob.glob(os.path.join(d, 'batch_*.json')))
        got = {}
        parse_err = []
        for fp in files:
            try:
                obj = json.load(open(fp, encoding='utf-8'))
            except Exception as e:
                parse_err.append((os.path.basename(fp), str(e)[:60]))
                continue
            items = obj.get('items') if isinstance(obj, dict) else obj
            for it in items or []:
                if it.get('sid'):
                    got[it['sid']] = it

        miss_sid, miss_bid, extra_bid, bad_tier = [], [], [], []
        bad_rate, bad_stress = [], []
        tier_c = {'narr': collections.Counter(), 'dlg': collections.Counter()}
        n_slot = 0
        for bname, t in tasks.items():
            trk = t.get('track', 'narr')
            ok_set = NARR_T if trk == 'narr' else DLG_T
            for it in t['items']:
                sid = it['sid']
                r = got.get(sid)
                if not r:
                    miss_sid.append(sid)
                    continue
                want = [s['bid'] for s in it['slots']]
                have = [p.get('bid') for p in (r.get('pause') or [])]
                for b in want:
                    if b not in have:
                        miss_bid.append(b)
                for b in have:
                    if b and b not in want:
                        extra_bid.append(b)
                for p in (r.get('pause') or []):
                    tv = str(p.get('tier') or '').strip().lower()
                    tier_c[trk][tv or '<empty>'] += 1
                    n_slot += 1
                    if tv not in ok_set:
                        bad_tier.append('%s %s/%s' % (p.get('bid'), trk, tv))

                # ---- rate：必须是 null 或 {"rate":0.72~0.84,"why":...} ----
                rt = r.get('rate')
                if rt is not None:
                    if not isinstance(rt, dict):
                        bad_rate.append('%s 不是对象(%r)' % (sid, rt))
                    else:
                        v = rt.get('rate')
                        if not isinstance(v, (int, float)):
                            bad_rate.append('%s rate 非数值(%r)' % (sid, v))
                        elif not (0.72 <= float(v) <= 0.84):
                            bad_rate.append('%s rate 越界(%s)' % (sid, v))
                        if not str(rt.get('why') or '').strip():
                            bad_rate.append('%s rate 缺 why' % sid)

                # ---- stress：tok 在范围内、level ∈ {1,2,3}、最多 3 个 ----
                sts = r.get('stress') or []
                ntok = len(it.get('tokens') or [])
                if len(sts) > 3:
                    bad_stress.append('%s 标了 %d 个' % (sid, len(sts)))
                for s in sts:
                    tk = s.get('tok')
                    lv = s.get('level')
                    if not isinstance(tk, int) or not (0 <= tk < ntok):
                        bad_stress.append('%s tok=%r 超界(0..%d)' % (sid, tk, ntok - 1))
                    if lv not in (1, 2, 3):
                        bad_stress.append('%s level=%r' % (sid, lv))

        tag = 'OK '
        if miss_sid or miss_bid or extra_bid or bad_tier or parse_err or bad_rate or bad_stress:
            tag = 'BAD'
            bad_any = True
        print('')
        print('[%s] %-6s files=%d sids=%d slots=%d' % (tag, name, len(files), len(got), n_slot))
        for trk in ('narr', 'dlg'):
            c = tier_c[trk]
            tot = sum(c.values())
            if not tot:
                continue
            top = max(c.values()) / tot
            flag = '  <- 退化(单档 %.0f%%)' % (100 * top) if top > 0.90 else ''
            print('   %-4s n=%-5d %s%s' % (trk, tot, dict(c), flag))
        if miss_sid:
            print('   缺 sid %d: %s' % (len(miss_sid), miss_sid[:6]))
        if miss_bid:
            print('   缺 bid %d: %s' % (len(miss_bid), miss_bid[:6]))
        if extra_bid:
            print('   多 bid %d: %s' % (len(extra_bid), extra_bid[:6]))
        if bad_tier:
            print('   越轨档 %d: %s' % (len(bad_tier), bad_tier[:6]))
        if bad_rate:
            print('   rate 不合格 %d: %s' % (len(bad_rate), bad_rate[:6]))
        if bad_stress:
            print('   stress 不合格 %d: %s' % (len(bad_stress), bad_stress[:6]))
        if parse_err:
            print('   解析失败 %d: %s' % (len(parse_err), parse_err[:4]))

    print('')
    print('有模型未达标，看上面 BAD 段' if bad_any else '全部达标')
    return 1 if bad_any else 0


if __name__ == '__main__':
    sys.exit(main())
