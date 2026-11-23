# -*- coding: utf-8 -*-
"""mt_emo_probe.py —— 情绪指纹可分离性探测。

目的：验证「情绪能不能从声学上客观测出来」，而不是让 LLM 说完就没人验。
素材：castle_fr_ref/（夏尔 4 种情绪 + Hooper 4 种，同一人跨情绪对照）

测 6 个维度（都是短片段稳健的）：
  f0_med   基频中位 Hz         —— 整体音区（紧张/低沉的直接反映）
  f0_span  p10~p90 跨度 st     —— 起伏幅度（激动大、平静小）
  f0_slope 段内平均斜率 st/s   —— 走向（上扬/下沉）
  rms      voiced RMS dB       —— 能量
  alpha    谱倾斜 dB           —— 音色明暗（紧喉→低，气声→高）
  hnr      谐噪比 dB           —— 气声程度（soft/begging 应更高）

用法：python mt_emo_probe.py [--win 1.5] [--hop 0.5]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf


def alpha_ratio(x, sr):
    """500-1000Hz 与 1000-5000Hz 的能量比（dB）。紧喉发声→负，气声→接近 0。"""
    if len(x) < int(0.05 * sr):
        return float('nan')
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    lo = X[(f >= 500) & (f < 1000)].mean()
    hi = X[(f >= 1000) & (f < 5000)].mean()
    if lo <= 0 or hi <= 0:
        return float('nan')
    return float(10 * np.log10(lo / hi))


def f0_slope(t, f):
    """连续 voiced 段内做线性回归，返回按段长加权的平均斜率（st/s，带符号）。"""
    if len(t) < 5:
        return float('nan')
    st = 12 * np.log2(np.maximum(f, 1e-6) / 100.0)
    # 切连续段（时间差 > 0.03s 断）
    idx = np.where(np.diff(t) > 0.03)[0]
    segs = np.split(np.arange(len(t)), idx + 1)
    slopes, weights = [], []
    for s in segs:
        if len(s) < 8:
            continue
        tt, yy = t[s], st[s]
        k = np.polyfit(tt - tt[0], yy, 1)[0]
        slopes.append(k)
        weights.append(tt[-1] - tt[0])
    if not slopes:
        return float('nan')
    return float(np.average(slopes, weights=weights))


def window_feats(x, sr):
    """单个窗口的 6 维特征。"""
    snd = parselmouth.Sound(np.ascontiguousarray(x, dtype=np.float64),
                            sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=500,
                        voicing_threshold=0.25, silence_threshold=0.03)
    f = np.asarray(p.selected_array['frequency'], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    v = f > 0
    if v.sum() < 8:
        return None
    fv, tv = f[v], t[v]

    h = snd.to_harmonicity_cc(time_step=0.01, minimum_pitch=60)
    hv = np.asarray(h.values[0], dtype=float)
    hv = hv[hv > -40]

    hop = max(1, int(0.02 * sr))
    n = len(x) // hop
    if n < 3:
        return None
    db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)) + 1e-12)
    ref = float(np.percentile(db, 90))
    voiced_db = db[db > ref - 20]
    if len(voiced_db) < 3:
        return None

    return dict(
        f0_med=float(np.median(fv)),
        f0_span=float(12 * np.log2(np.percentile(fv, 90) / max(np.percentile(fv, 10), 1e-6))),
        f0_slope=f0_slope(tv, fv),
        rms=float(np.median(voiced_db)),
        alpha=alpha_ratio(x, sr),
        hnr=float(np.median(hv)) if len(hv) else float('nan'),
    )


def file_feats(path, win, hop):
    x, sr = sf.read(path, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    nw = int(win * sr)
    nh = int(hop * sr)
    rows = []
    if len(x) < nw:
        r = window_feats(x, sr)
        return [r] if r else []
    for a in range(0, len(x) - nw + 1, nh):
        r = window_feats(x[a:a + nw], sr)
        if r:
            rows.append(r)
    return rows


KEYS = ['f0_med', 'f0_span', 'f0_slope', 'rms', 'alpha', 'hnr']
LABEL = {'f0_med': 'F0中位', 'f0_span': '跨度st', 'f0_slope': '斜率st/s',
         'rms': 'RMS', 'alpha': '谱倾斜', 'hnr': 'HNR'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='G:/_setup/castle_fr_ref')
    ap.add_argument('--win', type=float, default=1.5)
    ap.add_argument('--hop', type=float, default=0.5)
    ap.add_argument('--out', default='G:/_setup/_emo_probe.json')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.src, '*.wav')))
    if not files:
        print('没有素材')
        return

    per = {}
    print('%-30s %6s %5s' % ('文件', '时长', '窗数'))
    for f in files:
        k = os.path.basename(f)[:-4]
        rows = file_feats(f, a.win, a.hop)
        if not rows:
            print('%-30s  —     0  （全静音/太短）' % k)
            continue
        per[k] = rows
        dur = sf.info(f).duration
        print('%-30s %5.1fs %5d' % (k, dur, len(rows)))

    print()
    print('=' * 104)
    print('%-30s %5s ' % ('文件', 'n') +
          ' '.join('%9s' % LABEL[k] for k in KEYS))
    print('=' * 104)
    agg = {}
    for k in sorted(per):
        rows = per[k]
        med = {kk: float(np.nanmedian([r[kk] for r in rows])) for kk in KEYS}
        agg[k] = med
        print('%-30s %5d ' % (k, len(rows)) +
              ' '.join('%9.2f' % med[kk] for kk in KEYS))

    # 同一人跨情绪的离散度：若跨情绪差 > 同情绪内窗间差，说明可分离
    print()
    print('== 窗内抖动 vs 跨情绪差（判可分离性）==')
    print('%-9s %10s %10s %10s' % ('维度', '窗间sd', '跨情sd', '比值'))
    for kk in KEYS:
        within = []
        for k, rows in per.items():
            v = [r[kk] for r in rows if not np.isnan(r[kk])]
            if len(v) >= 3:
                within.append(np.std(v))
        m = [agg[k][kk] for k in agg]
        cross = np.std(m)
        w = float(np.nanmean(within)) if within else float('nan')
        ratio = cross / w if w > 1e-9 else float('nan')
        flag = ' ★可分离' if ratio >= 1.0 else ''
        print('%-9s %10.2f %10.2f %10.2f%s' % (LABEL[kk], w, cross, ratio, flag))

    json.dump(dict(per_window=per, per_file=agg,
                   win=a.win, hop=a.hop), open(a.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print()
    print('明细: %s' % a.out)


if __name__ == '__main__':
    main()
