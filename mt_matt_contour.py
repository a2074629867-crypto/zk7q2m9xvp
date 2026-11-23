# -*- coding: utf-8 -*-
"""mt_matt_contour.py —— 马修旁白的**句内 F0 轮廓**特征。

为什么需要这个（用户第 10~14 条）：
  之前的指标只有 span_st（幅度）和 head/tail slope（局部斜率）。
  幅度只能判「起伏不足」，判不了「起伏过多」和「起伏方向错」。
  要判这三件事，必须有**整句轮廓**：峰在哪、几个峰、句末降多少、形状是什么。

设计：
1. 用 VAD 切语音段（与 mt_matt_rhythm_probe.py 同一套参数），每段当一句。
2. F0 用 parselmouth，floor60/ceil250/vt=0.20 —— 旁白 HNR 只有 1.6dB，
   默认阈值只认 12% 的帧；这组参数是实测唯一能抓到 74Hz 基频的。
3. 只取 voiced 帧，按时间归一化到 0~1，再插值到 21 个等距点（便于形状比较）。
4. 特征：
   - peak_pos      F0 最高点的相对位置（0=句首 1=句末）
   - n_peaks       平滑后局部极大数（幅度阈 1.5 半音）
   - decl_st       句末 − 句首（半音，负=降调）
   - span_st       p95 − p5
   - slope_r2      线性拟合斜率与 R²（判「单调」还是「拱形」）
   - shape         分类：fall / arch / rise / wave / flat
5. 按段长分层，看形状是否随句长变。

输出 matt_contour.json
"""
import json
import sys

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call

sys.path.insert(0, r'G:/_setup')

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
OUT = r'G:/_setup/matt_contour.json'
NP = 21
SMOOTH = 3          # 滑动平均窗（21 点上的点数）
PEAK_PROM = 1.5     # 半音，低于此不算一个峰


def segs_of(path, thr=-35.0, fill=8, drop=12, sil=0.10):
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    x = x.mean(1)
    hop = int(0.010 * sr)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() + thr)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < fill:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < drop:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            segs.append((i * 0.010, j * 0.010))
            i = j
        else:
            i += 1
    out = []
    for a, b in segs:
        if b - a >= sil:
            out.append((a, b))
    return out, x, sr


def f0_track(x, sr, a, b):
    """返回 (t_rel, f0_st)，只含 voiced 帧，已相对该段中位转半音。"""
    snd = parselmouth.Sound(x[int(a * sr):int(b * sr)], sampling_frequency=sr)
    try:
        pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=250,
                              voicing_threshold=0.20, silence_threshold=0.03)
    except Exception:
        return None, None
    f = pit.selected_array['frequency']
    t = pit.xs()
    ok = f > 0
    if ok.sum() < 5:
        return None, None
    fv = f[ok]
    tv = t[ok]
    med = np.median(fv)
    if med <= 0:
        return None, None
    st = 12.0 * np.log2(fv / med)
    tr = (tv - tv.min()) / max(1e-6, tv.max() - tv.min())
    return tr, st


def smooth(y, k=SMOOTH):
    if len(y) < k:
        return y
    ker = np.ones(k) / k
    return np.convolve(y, ker, mode='same')


def shape_feats(tr, st):
    grid = np.linspace(0, 1, NP)
    yi = np.interp(grid, tr, st)
    ys = smooth(yi, SMOOTH)
    # ★ span 必须用**原始 voiced 帧**算，不能用插值后的 21 点。
    #   实测：插值会抹掉极值，导致 PSOLA 压缩后反而测出更大跨度
    #   （alpha 0.57 时 raw 5.14→0.746 单调，interp 6.84→1.111 不单调）。
    #   形状/峰位仍用插值后的平滑曲线，那是为了对齐时间轴。
    # ★ 主口径用 IQR（p75-p25），不用 p95-p5。
    #   实测 p95-p5 被 1~2 个异常帧拉爆：N0002 raw 13.92 但 IQR 2.55（倍频帧仅 1/57）、
    #   N0013 raw 16.73 但 IQR 4.21（倍频帧 0，是真实 F0 突变）。
    #   p95-p5 跨 6.7 倍、IQR 只跨 3 倍 ⇒ IQR 才是稳定量。
    span = float(np.percentile(st, 95) - np.percentile(st, 5))
    iqr = float(np.percentile(st, 75) - np.percentile(st, 25))
    decl = float(yi[-1] - yi[0])
    peak_pos = float(grid[int(np.argmax(ys))])
    # 线性拟合
    A = np.vstack([grid, np.ones_like(grid)]).T
    coef, *_ = np.linalg.lstsq(A, yi, rcond=None)
    pred = A @ coef
    ss = ((yi - yi.mean()) ** 2).sum()
    r2 = float(1 - ((yi - pred) ** 2).sum() / ss) if ss > 0 else 0.0
    slope = float(coef[0])  # 半音 / 归一化句长
    # 峰数：用 prominence 找局部极大
    n_peak = 0
    if len(ys) >= 3:
        for i in range(1, len(ys) - 1):
            if ys[i] >= ys[i - 1] and ys[i] > ys[i + 1]:
                # 与两侧最低点的落差
                lmin = ys[:i + 1].min()
                rmin = ys[i:].min()
                prom = ys[i] - max(lmin, rmin)
                if prom >= PEAK_PROM:
                    n_peak += 1
    # 形状分类
    if iqr < 1.2:
        shape = 'flat'
    elif r2 >= 0.55 and slope < 0:
        shape = 'fall'
    elif r2 >= 0.55 and slope > 0:
        shape = 'rise'
    elif 0.20 <= peak_pos <= 0.80 and decl < 1.0:
        shape = 'arch'
    else:
        shape = 'wave'
    return dict(span_st=span, iqr_st=iqr, decl_st=decl, peak_pos=peak_pos,
                n_peaks=n_peak, slope=slope, slope_r2=r2, shape=shape,
                ys=[round(float(v), 2) for v in ys])


def main():
    segs, x, sr = segs_of(MASTER)
    print('语音段 %d' % len(segs))
    rows = []
    for i, (a, b) in enumerate(segs):
        dur = b - a
        tr, st = f0_track(x, sr, a, b)
        if tr is None or len(tr) < 8:
            continue
        f = shape_feats(tr, st)
        f.update(i=i, t0=round(a, 2), dur=round(dur, 2))
        rows.append(f)
        if (i + 1) % 100 == 0:
            print('  %d/%d' % (i + 1, len(segs)), flush=True)

    print('有效 %d 段' % len(rows))
    if not rows:
        raise SystemExit('没有有效段')

    # ---- 总体分布
    def stat(key, fmt='%.2f'):
        v = np.array([r[key] for r in rows], float)
        return dict(p10=round(float(np.percentile(v, 10)), 2),
                    p25=round(float(np.percentile(v, 25)), 2),
                    median=round(float(np.median(v)), 2),
                    p75=round(float(np.percentile(v, 75)), 2),
                    p90=round(float(np.percentile(v, 90)), 2),
                    mean=round(float(v.mean()), 2))

    import collections
    shapes = collections.Counter(r['shape'] for r in rows)
    print('\n形状分布: %s' % dict(shapes))
    print('  %s' % {k: '%.0f%%' % (100.0 * v / len(rows)) for k, v in shapes.items()})

    print('\n%-10s %s' % ('span_st', stat('span_st')))
    print('%-10s %s' % ('decl_st', stat('decl_st')))
    print('%-10s %s' % ('peak_pos', stat('peak_pos')))
    print('%-10s %s' % ('n_peaks', stat('n_peaks')))
    print('%-10s %s' % ('slope_r2', stat('slope_r2')))

    # ---- 按段长分层
    buckets = [(0.3, 1.0), (1.0, 2.0), (2.0, 3.5), (3.5, 8.0)]
    print('\n=== 按段长分层 ===')
    print('%-10s %4s %8s %8s %8s %8s  %s' % (
        'dur', 'n', 'span_st', 'decl_st', 'peak_pos', 'r2', 'shape'))
    by_dur = {}
    for lo, hi in buckets:
        g = [r for r in rows if lo <= r['dur'] < hi]
        if not g:
            continue
        sh = collections.Counter(r['shape'] for r in g)
        top = sh.most_common(2)
        print('%-10s %4d %8.2f %8.2f %8.2f %8.2f  %s' % (
            '%.1f-%.1f' % (lo, hi), len(g),
            np.median([r['iqr_st'] for r in g]),
            np.median([r['decl_st'] for r in g]),
            np.median([r['peak_pos'] for r in g]),
            np.median([r['slope_r2'] for r in g]),
            ' '.join('%s:%.0f%%' % (k, 100.0 * v / len(g)) for k, v in top)))
        by_dur['%.1f-%.1f' % (lo, hi)] = dict(
            n=len(g),
            iqr_st=round(float(np.median([r['iqr_st'] for r in g])), 2),
            span_st=round(float(np.median([r['span_st'] for r in g])), 2),
            decl_st=round(float(np.median([r['decl_st'] for r in g])), 2),
            peak_pos=round(float(np.median([r['peak_pos'] for r in g])), 2),
            shape={k: round(v / len(g), 3) for k, v in sh.items()})

    # ---- 形状 vs 幅度
    print('\n=== 各形状的幅度与峰位 ===')
    by_shape = {}
    for s in ['fall', 'arch', 'wave', 'rise', 'flat']:
        g = [r for r in rows if r['shape'] == s]
        if not g:
            continue
        print('  %-6s n=%3d  iqr_st=%.2f  decl_st=%+.2f  peak_pos=%.2f  n_peaks=%.1f'
              % (s, len(g), np.median([r['iqr_st'] for r in g]),
                 np.median([r['decl_st'] for r in g]),
                 np.median([r['peak_pos'] for r in g]),
                 np.median([r['n_peaks'] for r in g])))
        by_shape[s] = dict(n=len(g),
                           iqr_st=round(float(np.median([r['iqr_st'] for r in g])), 2),
                           span_st=round(float(np.median([r['span_st'] for r in g])), 2),
                           decl_st=round(float(np.median([r['decl_st'] for r in g])), 2),
                           peak_pos=round(float(np.median([r['peak_pos'] for r in g])), 2),
                           n_peaks=round(float(np.median([r['n_peaks'] for r in g])), 1))

    out = dict(
        meta=dict(source=MASTER, n_seg=len(rows), np_points=NP,
                  f0_params='parselmouth ac, floor60 ceil250 vt0.20, step10ms',
                  peak_prom_st=PEAK_PROM,
                  note='每段当一个"句"处理。段 = VAD 语音段，不等于文本句。'),
        overall={k: stat(k) for k in ['iqr_st', 'span_st', 'decl_st', 'peak_pos', 'n_peaks', 'slope_r2']},
        shape_pct={k: round(v / len(rows), 3) for k, v in shapes.items()},
        by_dur=by_dur, by_shape=by_shape,
        rows=[{k: v for k, v in r.items() if k != 'ys'} for r in rows])
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→ %s' % OUT)


if __name__ == '__main__':
    main()
