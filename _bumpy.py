# -*- coding: utf-8 -*-
"""
起伏密度（无阈值口径）。

为什么要换：'峰密度' 用绝对突出度阈值（2st）时，灵敏度取决于说话人的音高跨度 ——
真人跨度 4.7st、我们 8.5st，同一个绝对阈值对真人更严，于是真人被少算、我们的倍数被高估。
这一次不用任何幅度阈值，只数**局部极大**（平滑后曲线上先升后降的转折点）：
  · 单调下降的一段（真人的常态：整句一路往下走）→ 0 个局部极大
  · 每个词都拱一下（我们的现状）→ 几乎每个词一个
这个量与音高跨度无关，只与"起伏次数"有关 —— 正好是用户定义的"词与词之间的差别"。

产物：_bumpy.json  每文件 dur / n_lm / lm_per_s / span / vr
       对我们自己的两版，另给"含≥1个局部极大的词 占比"（真人无词表，算不了）
"""
import json, os, sys, glob
import numpy as np
import soundfile as sf
import parselmouth
from multiprocessing import Pool

DOC = 'G:/_setup'
STEP = 0.01
SMOOTH = 2          # ±2 帧 = ±20ms 中值
MIN_GAP = 0.10      # 相邻局部极大最小间隔，防止平顶重复计数


def contour(path):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1:
        y = y.mean(1)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    p = snd.to_pitch(time_step=STEP, pitch_floor=60, pitch_ceiling=350)
    f0 = p.selected_array['frequency'].astype(float)
    v = f0 > 0
    if v.sum() < 30:
        return None
    st = np.where(v, 12 * np.log2(np.maximum(f0, 1) / 100.0), np.nan)
    s = st.copy()
    for i in range(SMOOTH, len(s) - SMOOTH):
        w = s[i - SMOOTH:i + SMOOTH + 1]
        w = w[~np.isnan(w)]
        if len(w):
            s[i] = np.median(w)
    idx = np.arange(len(s))
    good = ~np.isnan(s)
    vals = np.interp(idx, idx[good], s[good])
    return vals, good, len(y) / sr, st[good]


def local_max(vals, good, min_gap=MIN_GAP):
    w = max(1, int(round(min_gap / STEP / 2)))
    cand = []
    for k in range(w, len(vals) - w):
        if not good[k]:
            continue
        seg = vals[k - w:k + w + 1]
        if vals[k] >= seg.max() - 1e-9 and vals[k] > vals[k - 1] and vals[k] >= vals[k + 1]:
            cand.append((vals[k], k))
    cand.sort(reverse=True)
    kept = []
    for h, k in cand:
        if all(abs(k - k2) * STEP >= min_gap for _, k2 in kept):
            kept.append((h, k))
    return sorted(t for _, t in kept)


def job(arg):
    path, tag = arg
    r = contour(path)
    if r is None:
        return None
    vals, good, dur, voiced = r
    lm = local_max(vals, good)
    out = dict(path=path, tag=tag, dur=round(dur, 2),
               n_lm=len(lm), lm_per_s=round(len(lm) / max(dur, 0.1), 3),
               span=round(float(np.percentile(voiced, 95) - np.percentile(voiced, 5)), 2),
               vr=round(float(len(voiced) * STEP / max(dur, 0.1)), 3),
               lm_times=[round(t * STEP, 2) for t in lm])
    return out


if __name__ == '__main__':
    ids = set(l.strip() for l in open(f'{DOC}/_narr_ids716.json', encoding='utf-8')
              .read().strip('[]\n ').replace('"', '').split(',') if l.strip())
    tasks = [(p, 'human') for p in sorted(glob.glob('E:/ttsds/data/ref_human/*.wav'))]
    for tag, d in (('old', f'{DOC}/_audio_ch123/out'), ('new', f'{DOC}/_regen_final')):
        tasks += [(p, tag) for p in sorted(glob.glob(d + '/*.wav'))
                  if os.path.basename(p)[:-4] in ids]
    print('文件数', len(tasks), flush=True)
    res = []
    with Pool(6) as pool:
        for n, r in enumerate(pool.imap_unordered(job, tasks, chunksize=8), 1):
            if r:
                res.append(r)
            if n % 200 == 0:
                print('  ...', n, flush=True)
    json.dump(res, open(f'{DOC}/_bumpy.json', 'w', encoding='utf-8'))
    print('写入', len(res), flush=True)
