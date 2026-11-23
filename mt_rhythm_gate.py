# -*- coding: utf-8 -*-
"""S2 双向起伏闸门：太平 / 太陡 / 形状明显错 → 出 FIX 清单

判据来自 `_rhythm_bands.json`（分角色真人带，已做底噪归一）。
不设全局阈值 —— 旁白与对白、Charles 与 Hooper 各用自己的带。

判定（energy_span 双向）：
  PASS        p10 ≤ span ≤ p90
  WATCH_LOW   p05 ≤ span < p10
  WATCH_HIGH  p90 < span ≤ p95
  FIX_LOW     span < p05 − 2.5    ← 太平，要重生成（2.5dB 是跨 seed 噪声 p75）
  FIX_HIGH    span > p95 + 2.5    ← 太陡，要重生成
  UNMEAS      dur < 2.5s 或 n_win < 6

形状（只收四类明显错，逐条可判）：
  SHAPE_RISE  末段 300ms 斜率 > +3 st/s（陈述句；句尾是 ? 的跳过）
  SHAPE_OCT   八度跟踪伪影 ≥2 次
  SHAPE_CUT   结尾 5ms 跌落 ≥ 50dB（硬切）
  SHAPE_REV   方向反转率 > 真人带 p95（抖动异常）

不进单条判定：head/tail 的幅度、span_st 绝对值、21 点轮廓相关
  —— 实测跨 seed |差| 7.3 st/s，而要修的差距只有 2.3 st/s（信噪比 0.31）。
  这些只在组级（n≥20）与带中位比。

用法：
  python mt_rhythm_gate.py --dir G:/_setup/_mt_raw_s42 --ref narr
  python mt_rhythm_gate.py --chapter G:/_setup/_mt_out/ch1.wav --ref narr
  python mt_rhythm_gate.py --dir G:/_setup/ch123_final_llm --ref auto
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from narr_check import cut_units
from mt_rhythm_bands import measure

BANDS_DEFAULT = r'G:/_setup/_rhythm_bands.json'
OUT_DEFAULT = r'G:/_setup/_rhythm_gate.json'

MIN_DUR = 2.5
MIN_WIN = 6
# ★ 判定余量：跨 seed 的 energy_span |差| p50=1.4 / p75=2.5 dB。
#   实测全库 863 条里有 191 条判 FIX_HIGH，其中大量只超 0.1~0.3dB —— 那是噪声不是缺陷。
#   ⇒ 必须超出带界 MARGIN 才判 FIX，否则重生成等于追噪声。
MARGIN = 2.5         # dB，= 跨 seed |差| 的 p75
RISE_ST = 3.0        # 末段斜率 st/s
OCT_N = 2
CUT_DB = 50.0
GROUP_MIN = 20       # 组级形状比较的最低条数


def load_bands(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def role_of(name, default='narr'):
    """文件名 → 角色。L*/I* 是对白（查 ch123_plan），其余旁白。"""
    key = os.path.basename(name).split('.')[0]
    try:
        from ch123_plan import INNER, PLAN
        who = {'L%03d' % i: w for i, w, _, _ in PLAN}
        who.update({'I%02d' % i: w for i, (_, w, _, _) in enumerate(INNER)})
        if key in who:
            return 'charles' if who[key] == 'C' else 'hooper'
    except Exception:
        pass
    return default


def text_of(name):
    key = os.path.basename(name).split('.')[0]
    try:
        from ch123_plan import INNER, PLAN
        t = {'L%03d' % i: x for i, _, _, x in PLAN}
        t.update({'I%02d' % i: x for i, (_, _, _, x) in enumerate(INNER)})
        return t.get(key, '')
    except Exception:
        return ''


def judge(m, band, text=''):
    """返回 (verdict, why_list, shape_flags)"""
    span = m.get('energy_span')
    dur = m.get('dur') or 0
    nw = m.get('n_win') or 0
    e = band.get('energy_span') or {}
    shape = []
    if m.get('cut_drop') is not None and m['cut_drop'] >= CUT_DB:
        shape.append('SHAPE_CUT')
    if (m.get('oct_err') or 0) >= OCT_N:
        shape.append('SHAPE_OCT')
    ts = m.get('tail_slope')
    if ts is not None and ts > RISE_ST and not text.rstrip().endswith('?'):
        shape.append('SHAPE_RISE')
    rb = band.get('rev_rate') or {}
    if m.get('rev_rate') is not None and rb.get('p95') and m['rev_rate'] > rb['p95']:
        shape.append('SHAPE_REV')

    if dur < MIN_DUR or nw < MIN_WIN or span is None or not e:
        return 'UNMEAS', ['时长%.1fs/n窗%d' % (dur, nw)], shape
    lo_fix = e['p05'] - MARGIN
    hi_fix = e['p95'] + MARGIN
    if span < lo_fix:
        return 'FIX_LOW', ['%.1f < p05−%.1f = %.1f（差 %.1f）'
                           % (span, MARGIN, lo_fix, lo_fix - span)], shape
    if span > hi_fix:
        return 'FIX_HIGH', ['%.1f > p95+%.1f = %.1f（超 %.1f）'
                            % (span, MARGIN, hi_fix, span - hi_fix)], shape
    if span < e['p10']:
        return 'WATCH_LOW', ['%.1f < p10 %.1f' % (span, e['p10'])], shape
    if span > e['p90']:
        return 'WATCH_HIGH', ['%.1f > p90 %.1f' % (span, e['p90'])], shape
    return 'PASS', ['%.1f ∈ [%.1f, %.1f]' % (span, e['p10'], e['p90'])], shape


def units_from_dir(d, limit=0):
    files = sorted(glob.glob(os.path.join(d, '*.wav')))
    if limit:
        files = files[:limit]
    out = []
    for f in files:
        x, sr = sf.read(f, dtype='float32')
        if x.ndim > 1:
            x = x.mean(1)
        out.append((os.path.basename(f)[:-4], 0.0, len(x) / sr, x, sr))
    return out


def merge_units(us, min_dur=MIN_DUR, max_dur=10.0):
    """把过短的句子并成块。

    为什么必须并：能量 span 只在 dur≥2.5s 时才有判别力（短句起伏空间本来就小）。
    实测 ch1 按句切 435 段，其中 296 段 <2.5s ⇒ 68% 判不了。
    而我们的生成粒度本来就是「文本块」（p50 5.3s），所以并块才是同口径。
    """
    out = []
    a0 = None
    for a, b in us:
        if a0 is None:
            a0 = a
        if b - a0 >= min_dur or b - a >= max_dur:
            out.append((a0, b))
            a0 = None
    if a0 is not None:
        if out and us and us[-1][1] - a0 < min_dur:
            out[-1] = (out[-1][0], us[-1][1])
        else:
            out.append((a0, us[-1][1]))
    return out


def units_from_chapter(f, limit=0, merge=False):
    x, sr = sf.read(f, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    us = cut_units(x, sr)
    if merge:
        us = merge_units(us)
    if limit:
        us = us[:limit]
    return [('%s#%03d' % (os.path.basename(f)[:-4], i), a, b,
             x[int(a * sr):int(b * sr)], sr) for i, (a, b) in enumerate(us)]


SPAN_VOICED = False   # --span-voiced 时把 f0>0 也作为选帧条件（修「压平反判」）


def run(units, bands, ref, tag):
    rows = []
    for name, t0, t1, y, sr in units:
        role = ref if ref != 'auto' else role_of(name)
        band = bands.get(role) or {}
        m = measure(y, sr, role, span_voiced=SPAN_VOICED)
        v, why, shape = judge(m, band, text_of(name))
        rows.append(dict(unit=name, t0=round(t0, 2), t1=round(t1, 2),
                         role=role, verdict=v, why=why, shape=shape, **m))
    return rows


def summarize(rows):
    from collections import Counter
    c = Counter(r['verdict'] for r in rows)
    n = len(rows)
    sp = [r['energy_span'] for r in rows if r.get('energy_span') is not None]
    return dict(n=n, **{k: c.get(k, 0) for k in
                        ('PASS', 'WATCH_LOW', 'WATCH_HIGH', 'FIX_LOW', 'FIX_HIGH', 'UNMEAS')},
                span_p10=round(float(np.percentile(sp, 10)), 1) if sp else None,
                span_p50=round(float(np.median(sp)), 1) if sp else None,
                span_p90=round(float(np.percentile(sp, 90)), 1) if sp else None)


def group_shape(rows, band):
    """组级形状：只有 n≥20 才采信。"""
    out = {}
    for k in ('head_slope', 'tail_slope', 'span_st', 'rev_rate'):
        v = [r[k] for r in rows if r.get(k) is not None]
        if len(v) < GROUP_MIN:
            out[k] = dict(n=len(v), ok=False)
            continue
        bb = band.get(k) or {}
        out[k] = dict(n=len(v), ok=True, median=round(float(np.median(v)), 2),
                      band_p50=bb.get('p50'), band_p25=bb.get('p25'), band_p75=bb.get('p75'))
    return out


def write_md(path, tag, rows, summ, gshape, ref, bands=None):
    bands = bands or {}
    meta = bands.get('_meta') or {}
    band = bands.get(ref) if ref != 'auto' else None
    L = []
    L.append('# 起伏闸门 — %s\n' % tag)
    L.append('参考带：`%s`；底噪统一归一到 %s dBFS（跨源可比）\n'
             % (ref, meta.get('floor_target', '-')))
    if band:
        L.append('带样本 n=%d；FIX 界 = p05−%.1f / p95+%.1f（%.1f 是跨 seed 噪声 p75）\n'
                 % (band.get('n', 0), MARGIN, MARGIN, MARGIN))
        if band.get('n', 0) < 30:
            L.append('> ⚠ **该带样本仅 %d 条，分位数不稳**，FIX 判定只能作提示，不作硬闸门。\n'
                     % band.get('n', 0))
    L.append('## 总表\n')
    L.append('| n | PASS | WATCH_LOW | WATCH_HIGH | FIX_LOW | FIX_HIGH | UNMEAS | span p10/p50/p90 |')
    L.append('|---|---|---|---|---|---|---|---|')
    L.append('| %d | %d | %d | %d | **%d** | **%d** | %d | %s / %s / %s |'
             % (summ['n'], summ['PASS'], summ['WATCH_LOW'], summ['WATCH_HIGH'],
                summ['FIX_LOW'], summ['FIX_HIGH'], summ['UNMEAS'],
                summ['span_p10'], summ['span_p50'], summ['span_p90']))
    L.append('')
    fx = [r for r in rows if r['verdict'].startswith('FIX')]
    L.append('## FIX 清单（%d 条）\n' % len(fx))
    if fx:
        L.append('| unit | role | 判定 | energy_span | 依据 | 形状 | dur |')
        L.append('|---|---|---|---|---|---|---|')
        for r in fx:
            L.append('| %s | %s | %s | %s | %s | %s | %.1fs |'
                     % (r['unit'], r['role'], r['verdict'], r['energy_span'],
                        r['why'][0], ','.join(r['shape']) or '-', r['dur']))
    else:
        L.append('（无）')
    L.append('')
    L.append('## 组级形状（n≥%d 才采信）\n' % GROUP_MIN)
    L.append('| 指标 | n | 本批中位 | 带 p25–p75 | 带 p50 | 可采信 |')
    L.append('|---|---|---|---|---|---|')
    for k in ('head_slope', 'tail_slope', 'span_st', 'rev_rate'):
        g = gshape.get(k) or {}
        if g.get('ok'):
            L.append('| %s | %d | %s | %s–%s | %s | 是 |'
                     % (k, g['n'], g['median'], g['band_p25'], g['band_p75'], g['band_p50']))
        else:
            L.append('| %s | %d | - | - | - | 否（样本不足） |' % (k, g.get('n', 0)))
    L.append('')
    L.append('> 形状幅度不做单条判定：实测跨 seed |差| 7.3 st/s，目标差距 2.3 st/s（信噪比 0.31）。')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir')
    ap.add_argument('--chapter')
    ap.add_argument('--file')
    ap.add_argument('--ref', default='narr', help='narr|charles|hooper|auto')
    ap.add_argument('--bands', default=BANDS_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--merge', action='store_true',
                    help='整章模式：把过短句子并成 ≥2.5s 的块（否则 68%% 判不了）')
    ap.add_argument('--tag', default=None)
    ap.add_argument('--span-voiced', action='store_true',
                    help='选帧加 f0>0（对「整体压平」方向正确，但须重标带）')
    a = ap.parse_args()
    global SPAN_VOICED
    SPAN_VOICED = a.span_voiced

    bands = load_bands(a.bands)
    if a.file:
        x, sr = sf.read(a.file, dtype='float32')
        if x.ndim > 1:
            x = x.mean(1)
        units = [(os.path.basename(a.file)[:-4], 0.0, len(x) / sr, x, sr)]
        tag = a.tag or os.path.basename(a.file)[:-4]
    elif a.chapter:
        units = units_from_chapter(a.chapter, a.limit, merge=a.merge)
        tag = a.tag or os.path.basename(a.chapter)[:-4]
    elif a.dir:
        units = units_from_dir(a.dir, a.limit)
        tag = a.tag or os.path.basename(a.dir.rstrip('/\\'))
    else:
        ap.error('需要 --dir / --chapter / --file 之一')

    rows = run(units, bands, a.ref, tag)
    summ = summarize(rows)
    gshape = group_shape(rows, bands.get(a.ref if a.ref != 'auto' else 'narr', {}))
    print('[%s] n=%d  PASS %d / WATCH_LOW %d / WATCH_HIGH %d / FIX_LOW %d / FIX_HIGH %d / UNMEAS %d'
          % (tag, summ['n'], summ['PASS'], summ['WATCH_LOW'], summ['WATCH_HIGH'],
             summ['FIX_LOW'], summ['FIX_HIGH'], summ['UNMEAS']), flush=True)
    print('       span p10 %.1f / p50 %.1f / p90 %.1f' % (summ['span_p10'], summ['span_p50'], summ['span_p90']))
    for r in rows:
        if r['verdict'].startswith('FIX'):
            print('  FIX %-10s %-12s %s  %s %s'
                  % (r['unit'], r['verdict'], r['why'][0],
                     ','.join(r['shape']) or '', r['role']))

    out = a.out if a.out.endswith('.json') else a.out
    payload = dict(tag=tag, ref=a.ref, summary=summ, group_shape=gshape, rows=rows)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    md = os.path.splitext(out)[0] + '.md'
    write_md(md, tag, rows, summ, gshape, a.ref, bands)
    print('\n写出 %s\n     %s' % (out, md))


if __name__ == '__main__':
    main()
