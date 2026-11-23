# -*- coding: utf-8 -*-
"""句级韵律弧线分析（parselmouth / Praat 引擎）

目的：量化用户描述的三个听感
  ① "从句子开头到结尾的音调变化"  → 时间归一化的句子级 F0 弧线
  ② "最后的 right 从低向上"        → 句末 300ms 的 F0 斜率（半音/秒）
  ③ "延长音 / 演讲式分量感"        → 句内停顿结构 + 音节时长（另脚本）

用法:
  python -u prosody_arc.py --json out.json  file1.wav file2.wav ...
  python -u prosody_arc.py --json out.json --label "long and bright=path.wav"
"""
import argparse
import json
import os
import sys

import numpy as np
import parselmouth


def read_f0(path, floor=55.0, ceil=420.0, step=0.01):
    snd = parselmouth.Sound(path)
    # octave_jump_cost 调高 → 抑制倍频/半频跳变（气声低语下必备）
    pitch = snd.to_pitch_ac(time_step=step, pitch_floor=floor, pitch_ceiling=ceil,
                            voicing_threshold=0.35, octave_jump_cost=1.0,
                            octave_cost=0.01)
    f0 = np.asarray(pitch.selected_array['frequency'], dtype=np.float64)
    t = np.asarray(pitch.xs(), dtype=np.float64)
    return f0, t, float(snd.duration)


def clean_f0(f0, max_dev_st=7.0):
    """剔除离群帧（倍频/半频误判）。返回 (清理后 f0, 剔除帧数)。
    判据：偏离整段中位数 > max_dev_st 半音（≈1.5× 频率比）的帧判为错误。"""
    out = f0.copy()
    v = f0 > 0
    nv = int(v.sum())
    if nv < 8:
        return out, 0
    vi = np.where(v)[0]
    fv = f0[v]
    for _ in range(2):
        med = float(np.median(fv))
        if med <= 0:
            break
        st = 12.0 * np.log2(fv / med)
        good = np.abs(st) <= max_dev_st
        if good.sum() < 8:
            break
        fv = fv[good]
    keep = np.zeros(len(f0), dtype=bool)
    keep[vi[np.abs(12.0 * np.log2(f0[vi] / float(np.median(fv)))) <= max_dev_st]] = True
    out[~keep] = 0.0
    return out, nv - int(keep.sum())


def segments(f0, t, min_gap=0.22, min_len=0.35):
    """按浊音连续性切分短语（≈ 句子/小句）。返回 [(i0,i1)] 索引区间。"""
    voiced = f0 > 0
    idx = np.where(voiced)[0]
    if len(idx) == 0:
        return []
    # 以未浊音间隔 > min_gap 断句
    segs = []
    start = idx[0]
    prev = idx[0]
    for i in idx[1:]:
        if t[i] - t[prev] > min_gap:
            segs.append((start, prev))
            start = i
        prev = i
    segs.append((start, prev))
    # 过滤过短
    out = []
    for a, b in segs:
        if t[b] - t[a] >= min_len:
            out.append((a, b))
    return out


def seg_stats(f0, t, a, b):
    """一个短语段内的轮廓统计（全部以段内中位数为基准，单位半音）"""
    f = f0[a:b + 1].copy()
    tt = t[a:b + 1]
    v = f > 0
    if v.sum() < 8:
        return None
    # 仅用浊音点，线性插值成等间隔曲线
    fv = f[v]
    tv = tt[v]
    med = float(np.median(fv))
    if med <= 0:
        return None
    st = 12.0 * np.log2(fv / med)
    dur = float(tv[-1] - tv[0])
    if dur <= 0:
        return None
    # 时间归一化到 21 个点（0%..100%）
    grid = np.linspace(0, 1, 21)
    prof = np.interp(grid, (tv - tv[0]) / dur, st)
    # 句末 300ms 斜率
    tail_m = tv >= (tv[-1] - 0.30)
    slope = 0.0
    if tail_m.sum() >= 4 and (tv[-1] - tv[tail_m][0]) > 0.05:
        A = np.vstack([tv[tail_m], np.ones(tail_m.sum())]).T
        slope = float(np.linalg.lstsq(A, st[tail_m], rcond=None)[0][0])
    head_m = tv <= (tv[0] + 0.30)
    slope_head = 0.0
    if head_m.sum() >= 4 and (tv[head_m][-1] - tv[0]) > 0.05:
        A = np.vstack([tv[head_m], np.ones(head_m.sum())]).T
        slope_head = float(np.linalg.lstsq(A, st[head_m], rcond=None)[0][0])
    # 段内停顿（未浊音累计）
    gap = float(dur) - float(np.sum(np.diff(tv))) if len(tv) > 1 else 0.0
    return dict(
        dur=round(dur, 3),
        f0_med=round(med, 1),
        f0_lo=round(float(np.percentile(fv, 5)), 1),
        f0_hi=round(float(np.percentile(fv, 95)), 1),
        span_st=round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2),
        std_st=round(float(np.std(st)), 2),
        start_st=round(float(prof[0]), 2),
        q25_st=round(float(prof[5]), 2),
        mid_st=round(float(prof[10]), 2),
        q75_st=round(float(prof[15]), 2),
        end_st=round(float(prof[-1]), 2),
        tail_slope_st_s=round(slope, 2),
        head_slope_st_s=round(slope_head, 2),
        arc_st=round(float(prof[-1] - prof[0]), 2),   # 句子级净变化
        prof=[round(float(x), 2) for x in prof],
    )


SPARK = "▁▂▃▄▅▆▇█"


def spark(vals):
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-6:
        return SPARK[3] * len(vals)
    out = []
    for v in vals:
        k = int(round((v - lo) / (hi - lo) * (len(SPARK) - 1)))
        out.append(SPARK[k])
    return "".join(out)


def analyze(path, floor=55.0, ceil=420.0):
    f0, t, dur = read_f0(path, floor, ceil)
    f0, nrej = clean_f0(f0)
    segs = segments(f0, t)
    rows = []
    for a, b in segs:
        s = seg_stats(f0, t, a, b)
        if s:
            s['t0'] = round(float(t[a]), 2)
            s['t1'] = round(float(t[b]), 2)
            rows.append(s)
    return dict(path=path, dur=round(dur, 2), n_seg=len(rows),
                n_rejected=nrej, segs=rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    ap.add_argument('--label', action='append', default=[], help='名字=路径')
    ap.add_argument('--json', default='')
    ap.add_argument('--floor', type=float, default=55.0)
    ap.add_argument('--ceil', type=float, default=420.0)
    a = ap.parse_args()

    jobs = []
    for lb in a.label:
        nm, _, p = lb.partition('=')
        jobs.append((nm, p))
    for p in a.files:
        jobs.append((os.path.basename(p), p))

    allout = []
    for nm, p in jobs:
        try:
            r = analyze(p, a.floor, a.ceil)
        except Exception as e:
            print('ERR %-28s %s: %s' % (nm, type(e).__name__, e))
            continue
        r['label'] = nm
        allout.append(r)
        print('=== %s  (%.1fs, %d 段, 剔除 %d 帧) ===' %
              (nm, r['dur'], r['n_seg'], r['n_rejected']))
        for i, s in enumerate(r['segs']):
            print('  #%d %5.2f-%5.2fs  f0=%5.1fHz  跨度%5.2f  弧线%+6.2f  '
                  '末斜率%+6.2f st/s' %
                  (i + 1, s['t0'], s['t1'], s['f0_med'], s['span_st'],
                   s['arc_st'], s['tail_slope_st_s']))
            print('     轮廓(半音, 时间0→100%%)  %s' % spark(s['prof']))
            print('     %s' % ' '.join('%+5.1f' % x for x in s['prof']))
        print()

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(allout, f, ensure_ascii=False, indent=1)
        print('已写出 %s' % a.json)


if __name__ == '__main__':
    main()
