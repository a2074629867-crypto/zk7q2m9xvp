# -*- coding: utf-8 -*-
"""从 Wonder 真实语料里学「马修的句级语调原型」。

产出：
  contour_bank.json
    - by_class: 按句末标点分类的 21 点平均轮廓（半音，中位数基准）
    - stats:    每类的跨度 / 起伏 / 句末斜率 分布
    - elong:    句末延长比例（用能量包络的音节核间距估计）

用途：给「没有 donor 的真实录音」的任意生成文本，注入他的句级语调形状。
"""
import json
import os
import re
import sys

import numpy as np
import parselmouth

sys.path.insert(0, r'G:/_setup')
from prosody_arc import read_f0, clean_f0, segments  # noqa: E402
from transplant_prosody import norm_contour  # noqa: E402

LIST = r'G:/GPT-SoVITS/_dataset/wonder.list'
OUT = r'G:/_setup/contour_bank.json'
NPT = 21


def syll_nuclei(snd, min_gap=0.06):
    """用强度包络找音节核时间点（近似）。"""
    inten = snd.to_intensity(minimum_pitch=100.0, time_step=0.01)
    v = np.asarray(inten.values).ravel()
    t = np.asarray(inten.xs())
    if len(v) < 5:
        return np.array([])
    thr = float(np.percentile(v, 20)) + 0.35 * (float(v.max()) - float(np.percentile(v, 20)))
    peaks = []
    i = 1
    last = -9
    while i < len(v) - 1:
        if v[i] > thr and v[i] >= v[i - 1] and v[i] > v[i + 1]:
            if t[i] - last > min_gap:
                peaks.append(t[i])
                last = t[i]
            i += 3
        else:
            i += 1
    return np.array(peaks)


def main():
    rows = []
    for ln in open(LIST, encoding='utf-8'):
        p = ln.rstrip('\n').split('|')
        if len(p) >= 4:
            rows.append((p[0], p[3]))
    print('语料 %d 条' % len(rows))

    by_class = {}
    skipped = 0
    for path, text in rows:
        text = text.strip()
        if not os.path.exists(path):
            skipped += 1
            continue
        # 句末标点分类
        tail = text.rstrip('"\') ').rstrip()
        if tail.endswith(','):
            cls = 'comma'
        elif tail.endswith('?'):
            cls = 'question'
        elif tail.endswith('!'):
            cls = 'exclam'
        elif tail.endswith('.'):
            cls = 'period'
        else:
            cls = 'none'
        try:
            f0, t, dur = read_f0(path)
            f0, _ = clean_f0(f0)
        except Exception:
            skipped += 1
            continue
        segs = segments(f0, t, min_gap=0.30, min_len=0.60)
        if not segs:
            skipped += 1
            continue
        # 用最后一个（最长的）段作为代表
        a, b = max(segs, key=lambda s: t[s[1]] - t[s[0]])
        f = f0[a:b + 1]
        tt = t[a:b + 1]
        v = f > 0
        if v.sum() < 10:
            skipped += 1
            continue
        u, st, med = norm_contour(tt[v], f[v])
        prof = np.interp(np.linspace(0, 1, NPT), u, st)
        # 句末 25% 斜率
        tailm = u >= 0.75
        slope = 0.0
        if tailm.sum() >= 4:
            A = np.vstack([u[tailm], np.ones(tailm.sum())]).T
            slope = float(np.linalg.lstsq(A, st[tailm], rcond=None)[0][0])
        # 句末延长：最后 2 个音节核间距 / 全部音节核间距中位数
        elong = 1.0
        try:
            snd = parselmouth.Sound(path)
            pk = syll_nuclei(snd)
            if len(pk) >= 4:
                gaps = np.diff(pk)
                med_g = float(np.median(gaps))
                if med_g > 1e-4:
                    elong = float(np.mean(gaps[-2:]) / med_g)
        except Exception:
            pass
        rec = dict(prof=[round(float(x), 3) for x in prof],
                   span=round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2),
                   std=round(float(np.std(st)), 2),
                   tail_slope=round(slope, 2),
                   end_st=round(float(prof[-1]), 2),
                   peak_pos=round(float(np.argmax(prof)) / (NPT - 1), 2),
                   elong=round(elong, 3),
                   dur=round(dur, 2))
        by_class.setdefault(cls, []).append(rec)

    out = {'n_total': len(rows), 'n_skipped': skipped, 'by_class': {}}
    for cls, recs in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        profs = np.array([r['prof'] for r in recs])
        out['by_class'][cls] = dict(
            n=len(recs),
            mean_prof=[round(float(x), 3) for x in profs.mean(axis=0)],
            span_mean=round(float(np.mean([r['span'] for r in recs])), 2),
            span_med=round(float(np.median([r['span'] for r in recs])), 2),
            std_mean=round(float(np.mean([r['std'] for r in recs])), 2),
            tail_slope_mean=round(float(np.mean([r['tail_slope'] for r in recs])), 2),
            end_st_mean=round(float(np.mean([r['end_st'] for r in recs])), 2),
            peak_pos_mean=round(float(np.mean([r['peak_pos'] for r in recs])), 2),
            elong_mean=round(float(np.mean([r['elong'] for r in recs])), 3),
            elong_med=round(float(np.median([r['elong'] for r in recs])), 3),
        )

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    SP = '▁▂▃▄▅▆▇█'

    def spark(v):
        lo, hi = min(v), max(v)
        if hi - lo < 1e-6:
            return SP[3] * len(v)
        return ''.join(SP[int(round((x - lo) / (hi - lo) * 7))] for x in v)

    print('跳过 %d 条' % skipped)
    for cls, d in out['by_class'].items():
        print('\n=== %-9s n=%-4d ===' % (cls, d['n']))
        print('  平均轮廓 %s' % spark(d['mean_prof']))
        print('  %s' % ' '.join('%+5.1f' % x for x in d['mean_prof']))
        print('  跨度均值 %.2f  起伏均值 %.2f  句末斜率均值 %+.2f  '
              '末值均值 %+.2f  峰值位置 %.2f' %
              (d['span_mean'], d['std_mean'], d['tail_slope_mean'],
               d['end_st_mean'], d['peak_pos_mean']))
        print('  句末延长比 均值 %.3f  中位 %.3f' % (d['elong_mean'], d['elong_med']))
    print('\n已写出 %s' % OUT)


if __name__ == '__main__':
    main()
