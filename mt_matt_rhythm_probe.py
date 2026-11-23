# -*- coding: utf-8 -*-
"""mt_matt_rhythm_probe.py —— 不依赖标点的韵律建模。

为什么不按「标点 → 秒数」提炼：
  实测 wonder_final.json 的标点几乎全缺（562 处停顿里 545 处 prev_punct=None），
  因为切片按 GSV 边界切，不在标点处；词性分组 eta² 只有 0.03~0.05。

改成按「语音段」建模——韵律的本质是段的组织，不是标点：
  一段话 = 若干语音段（breath group）+ 段间停顿
  每个段测：时长、音节数、F0 跨度/走向、能量跨度
  每个停顿测：时长、前后段长度比、前后 F0 差（是否重置）

要回答的问题（全部用数据）：
  Q1 停顿时长能否被「前后段长度」预测？（节奏平衡）
  Q2 停顿后 F0 是否重置？重置多少？
  Q3 段内语速是否随段长变化？（长段更快？）
  Q4 段末是否有延长/降调？（收束标记）
"""
import json
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, r'G:/_setup')

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
OUT = r'G:/_setup/matt_rhythm_probe.json'
SR = 32000


def segs_of(path, thr=-35.0, fill=8, drop=12):
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
    while i < n:
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return segs, x, sr


def f0_of(x, sr):
    snd = parselmouth.Sound(np.ascontiguousarray(x.astype(np.float32)),
                            sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=250,
                        voicing_threshold=0.20, silence_threshold=0.03)
    f = np.asarray(p.selected_array['frequency'], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    return f, t


def seg_feat(x, sr, a, b):
    """一个语音段的韵律特征。"""
    i0, i1 = int(a * sr), int(b * sr)
    y = x[i0:i1]
    if len(y) < int(0.12 * sr):
        return None
    dur = len(y) / sr
    db = 20 * np.log10(np.sqrt(np.maximum(y.astype(np.float64) ** 2, 1e-20)))
    # 能量：段内 21 点轮廓
    k = max(1, len(db) // 21)
    prof = [float(np.percentile(db[i * k:(i + 1) * k], 90)) for i in range(min(21, len(db) // k))]
    esp = (max(prof) - min(prof)) if len(prof) >= 3 else None

    f, t = f0_of(y, sr)
    v = f > 0
    if v.sum() < 8:
        return dict(dur=round(dur, 2), esp=None if esp is None else round(esp, 1),
                    f0_med=None, span_st=None, head=None, tail=None, slope=None)
    fv = f[v]
    med = float(np.median(fv))
    st = 12 * np.log2(np.maximum(fv, 1e-6) / med)
    span = float(np.percentile(st, 95) - np.percentile(st, 5))

    # 25 窗斜率，取首尾四分之一
    nw, nh = 25, 6
    sl = []
    for i in range(0, len(f) - nw + 1, nh):
        vv = v[i:i + nw]
        if vv.sum() < nw * 0.7:
            continue
        tt = t[i:i + nw][vv]
        yy = 12 * np.log2(np.maximum(f[i:i + nw][vv], 1e-6) / med)
        if tt[-1] - tt[0] < 0.15:
            continue
        sl.append(np.polyfit(tt - tt[0], yy, 1)[0])
    head = tail = None
    if len(sl) >= 4:
        q = max(1, len(sl) // 4)
        head = float(np.mean(sl[:q]))
        tail = float(np.mean(sl[-q:]))
    return dict(dur=round(dur, 2), esp=None if esp is None else round(esp, 1),
                f0_med=round(med, 1), span_st=round(span, 2),
                head=None if head is None else round(head, 2),
                tail=None if tail is None else round(tail, 2),
                slope=None if head is None else round(float(np.mean(sl)), 2))


def main():
    print('VAD …', flush=True)
    segs, x, sr = segs_of(MASTER)
    print('语音段 %d  总时长 %.1fs' % (len(segs), len(x) / sr), flush=True)

    print('逐段测 F0 …', flush=True)
    feats = []
    for i, (a, b) in enumerate(segs):
        f = seg_feat(x, sr, a, b)
        feats.append(f)
        if (i + 1) % 100 == 0:
            print('  %d/%d' % (i + 1, len(segs)), flush=True)

    # 停顿 = 相邻段之间
    rows = []
    for i in range(len(segs) - 1):
        gap = segs[i + 1][0] - segs[i][1]
        if gap < 0.10:
            continue
        A, B = feats[i], feats[i + 1]
        if not A or not B:
            continue
        rows.append(dict(
            gap=round(gap, 3),
            a_dur=A['dur'], b_dur=B['dur'],
            a_esp=A['esp'], b_esp=B['esp'],
            a_span=A['span_st'], b_span=B['span_st'],
            a_f0=A['f0_med'], b_f0=B['f0_med'],
            a_tail=A['tail'], b_head=B['head'],
            f0_delta=(None if (A['f0_med'] is None or B['f0_med'] is None)
                      else round(12 * np.log2(B['f0_med'] / A['f0_med']), 2)),
        ))
    print('停顿 %d 处' % len(rows), flush=True)

    g = np.array([r['gap'] for r in rows])
    print('\n=== Q1 停顿能否被前后段长度预测 ===')
    ad = np.array([r['a_dur'] for r in rows])
    bd = np.array([r['b_dur'] for r in rows])
    for name, v in (('前段时长', ad), ('后段时长', bd), ('前后总长', ad + bd),
                    ('前后长度差', np.abs(ad - bd))):
        print('  gap ~ %-8s  Pearson %.3f  Spearman %.3f'
              % (name, np.corrcoef(g, v)[0, 1],
                 np.corrcoef(np.argsort(np.argsort(g)), np.argsort(np.argsort(v)))[0, 1]))
    # 分桶看
    print('  按前后总长分桶:')
    tot = ad + bd
    for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 9), (9, 99)):
        m = (tot >= lo) & (tot < hi)
        if m.sum() >= 10:
            print('    %.0f~%.0fs  n=%3d  gap 中位 %.2f  IQR %.2f~%.2f'
                  % (lo, hi, m.sum(), np.median(g[m]),
                     np.percentile(g[m], 25), np.percentile(g[m], 75)))

    print('\n=== Q2 停顿后 F0 是否重置 ===')
    fd = np.array([r['f0_delta'] for r in rows if r['f0_delta'] is not None])
    print('  后段 F0 − 前段 F0（半音）: n=%d 中位 %+.2f  p25 %+.2f p75 %+.2f'
          % (len(fd), np.median(fd), np.percentile(fd, 25), np.percentile(fd, 75)))
    print('  升高占比 %.0f%%   持平分（|Δ|<0.5st）%.0f%%'
          % (100 * (fd > 0.5).mean(), 100 * (np.abs(fd) <= 0.5).mean()))
    print('  按停顿长短:')
    sub = [r for r in rows if r['f0_delta'] is not None]
    for lo, hi in ((0.10, 0.30), (0.30, 0.60), (0.60, 1.20), (1.20, 99)):
        v = np.array([r['f0_delta'] for r in sub if lo <= r['gap'] < hi])
        if len(v) >= 10:
            print('    %.2f~%.2fs  n=%3d  ΔF0 中位 %+.2f  升高 %.0f%%'
                  % (lo, hi, len(v), np.median(v), 100 * (v > 0.5).mean()))

    print('\n=== Q3 段内语速 vs 段长 ===')
    d = np.array([f['dur'] for f in feats if f])
    s = np.array([f['span_st'] for f in feats if f and f['span_st'] is not None])
    print('  段长 p10 %.2f p50 %.2f p90 %.2f' % tuple(np.percentile(d, [10, 50, 90])))
    fv = [f for f in feats if f and f['span_st'] is not None]
    d2 = np.array([f['dur'] for f in fv])
    ss = np.array([f['span_st'] for f in fv])
    for lo, hi in ((0.3, 1.0), (1.0, 2.0), (2.0, 3.5), (3.5, 6.0), (6.0, 99)):
        m = (d2 >= lo) & (d2 < hi)
        if m.sum() >= 10:
            print('    段长 %.1f~%.1fs  n=%3d  span_st 中位 %.2f  esp 中位 %.1f'
                  % (lo, hi, m.sum(), np.median(ss[m]),
                     np.median([f['esp'] for f, ok in zip(fv, m) if ok and f['esp'] is not None] or [0])))

    print('\n=== Q4 段末收束标记（tail 斜率）===')
    tl = np.array([f['tail'] for f in feats if f and f['tail'] is not None])
    hd = np.array([f['head'] for f in feats if f and f['head'] is not None])
    print('  head p25 %+.2f 中位 %+.2f p75 %+.2f  (n=%d)'
          % (np.percentile(hd, 25), np.median(hd), np.percentile(hd, 75), len(hd)))
    print('  tail p25 %+.2f 中位 %+.2f p75 %+.2f  (n=%d)'
          % (np.percentile(tl, 25), np.median(tl), np.percentile(tl, 75), len(tl)))
    print('  head>0 占 %.0f%%   tail<0 占 %.0f%%'
          % (100 * (hd > 0).mean(), 100 * (tl < 0).mean()))

    json.dump(dict(meta=dict(master=MASTER, n_seg=len(segs), n_gap=len(rows),
                             vadv='thr=-35dB fill=8 drop=12'),
                   segs=[dict(a=round(a, 2), b=round(b, 2), **{k: v for k, v in f.items()})
                         for (a, b), f in zip(segs, feats) if f],
                   gaps=rows), open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n写出', OUT)


if __name__ == '__main__':
    main()
