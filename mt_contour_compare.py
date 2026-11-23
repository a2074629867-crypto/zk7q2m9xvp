# -*- coding: utf-8 -*-
"""mt_contour_compare.py —— 用**同一测量函数**对比马修母带与我们的生成。

为什么必须同口径：
  _gate_narr.json 里我们的 span_p50=16.1，matt_prosody_rules 里马修是 6 左右，
  但那是两个不同函数、不同窗口长度（我们 7.5s 单元 vs 马修 2s 段）测出来的。
  长窗口天然包含更多极值，直接比会把差异夸大 2~3 倍。

做法：
  对每个 wav 用与 mt_matt_contour.py 完全相同的 VAD 参数切语音段，
  每段算同一套轮廓特征（span_st / decl_st / peak_pos / n_peaks / shape），
  再与马修的 627 段逐项对比。

同时输出：
- 按段长分层的对比（段长是最大混淆因子）
- 跨 seed 稳定性（同一单元在不同 seed 的 span_st 差）
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, r'G:/_setup')
from mt_matt_contour import segs_of, f0_track, shape_feats  # noqa: E402

MATT = r'G:/_setup/matt_contour.json'
BUCKETS = [(0.3, 1.0), (1.0, 2.0), (2.0, 3.5), (3.5, 99)]


def feats_of_wav(path):
    segs, x, sr = segs_of(path)
    out = []
    for a, b in segs:
        tr, st = f0_track(x, sr, a, b)
        if tr is None or len(tr) < 8:
            continue
        f = shape_feats(tr, st)
        f['dur'] = round(b - a, 2)
        out.append(f)
    return out


def dist(rows, key):
    v = np.array([r[key] for r in rows], float)
    if len(v) == 0:
        return {}
    return dict(n=len(v),
                p10=round(float(np.percentile(v, 10)), 2),
                p25=round(float(np.percentile(v, 25)), 2),
                p50=round(float(np.median(v)), 2),
                p75=round(float(np.percentile(v, 75)), 2),
                p90=round(float(np.percentile(v, 90)), 2),
                mean=round(float(v.mean()), 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', nargs='+', default=[r'G:/_setup/_mt_raw_s42'])
    ap.add_argument('--out', default=r'G:/_setup/matt_contour_compare.json')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()

    matt = json.load(open(MATT, encoding='utf-8'))
    mrows = matt['rows']
    print('马修 %d 段' % len(mrows))

    ours = []
    per_dir = {}
    for d in a.dir:
        files = sorted(glob.glob(os.path.join(d, '*.wav')))
        if a.limit:
            files = files[:a.limit]
        print('%s: %d wav' % (os.path.basename(d), len(files)))
        acc = []
        for i, f in enumerate(files):
            try:
                acc += feats_of_wav(f)
            except Exception as e:
                print('  !! %s: %s' % (os.path.basename(f), e))
            if (i + 1) % 100 == 0:
                print('  %d/%d  段 %d' % (i + 1, len(files), len(acc)), flush=True)
        per_dir[os.path.basename(d)] = acc
        ours += acc
        print('  → 段 %d' % len(acc))

    print('\n我们合计 %d 段' % len(ours))

    print('\n=== 段级分布对比（同口径）===')
    print('%-9s %-6s %6s %6s %6s %6s %6s %6s' % (
        'metric', 'who', 'n', 'p10', 'p25', 'p50', 'p75', 'p90'))
    cmp = {}
    for key in ['iqr_st', 'span_st', 'decl_st', 'peak_pos', 'n_peaks', 'slope_r2']:
        dm, do = dist(mrows, key), dist(ours, key)
        cmp[key] = dict(matt=dm, ours=do)
        for who, dd in (('matt', dm), ('ours', do)):
            print('%-9s %-6s %6d %6.2f %6.2f %6.2f %6.2f %6.2f' % (
                key, who, dd['n'], dd['p10'], dd['p25'], dd['p50'],
                dd['p75'], dd['p90']))
        print('%-9s %-6s %6s %6s %6s %+6.2f %6s %6s' % (
            '', 'diff', '', '', '', do['p50'] - dm['p50'], '', ''))

    print('\n=== 形状分布 ===')
    sm = collections.Counter(r['shape'] for r in mrows)
    so = collections.Counter(r['shape'] for r in ours)
    print('%-7s %8s %8s' % ('shape', 'matt', 'ours'))
    shapes = {}
    for s in ['wave', 'arch', 'flat', 'fall', 'rise']:
        pm = 100.0 * sm.get(s, 0) / len(mrows)
        po = 100.0 * so.get(s, 0) / max(1, len(ours))
        print('%-7s %7.0f%% %7.0f%%' % (s, pm, po))
        shapes[s] = dict(matt_pct=round(pm, 1), ours_pct=round(po, 1))

    print('\n=== 按段长分层（iqr_st）===')
    print('%-10s %5s %7s %5s %7s %7s' % ('dur', 'n_m', 'matt', 'n_o', 'ours', 'ratio'))
    by_dur = {}
    for lo, hi in BUCKETS:
        gm = [r['iqr_st'] for r in mrows if lo <= r['dur'] < hi]
        go = [r['iqr_st'] for r in ours if lo <= r['dur'] < hi]
        if not gm or not go:
            continue
        mm, mo = float(np.median(gm)), float(np.median(go))
        print('%-10s %5d %7.2f %5d %7.2f %7.2f' % (
            '%.1f-%.1f' % (lo, hi), len(gm), mm, len(go), mo, mo / mm))
        by_dur['%.1f-%.1f' % (lo, hi)] = dict(
            n_matt=len(gm), matt=round(mm, 2), n_ours=len(go),
            ours=round(mo, 2), ratio=round(mo / mm, 2))

    # ---- 跨 seed 稳定性
    print('\n=== 跨 seed 稳定性（同一单元不同 seed 的 span_st 差）===')
    if len(per_dir) > 1:
        # 按段序号对齐（各目录文件同名，段序号同序）
        base = list(per_dir.values())[0]
        cross = {}
        for name, rows in per_dir.items():
            if rows is base:
                continue
            n = min(len(base), len(rows))
            if n < 10:
                continue
            d = [abs(base[i]['span_st'] - rows[i]['span_st']) for i in range(n)]
            cross[name] = dict(n=n, med_abs=round(float(np.median(d)), 2),
                               p75=round(float(np.percentile(d, 75)), 2))
            print('  %-16s n=%d  |Δspan| 中位 %.2f  p75 %.2f' % (
                name, n, np.median(d), np.percentile(d, 75)))
    else:
        cross = {}
        print('  只有一个目录，跳过')

    out = dict(meta=dict(matt_source=MATT, ours_dirs=a.dir,
                         n_matt=len(mrows), n_ours=len(ours),
                         buckets=[list(b) for b in BUCKETS]),
               dist=cmp, shapes=shapes, by_dur=by_dur, cross_seed=cross)
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→ %s' % a.out)


if __name__ == '__main__':
    main()
