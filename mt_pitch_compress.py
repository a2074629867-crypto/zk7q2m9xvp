# -*- coding: utf-8 -*-
"""mt_pitch_compress.py —— 后期压缩 F0 起伏幅度（span_st）。

为什么必须后期做：
  同一文本换 seed，span_st 的抖动中位 4.37 半音（n=46，降/升 24/20 约各半），
  而我们与马修的差距是 4.39 半音 ⇒ SNR≈1.0，换 seed 修起伏等于抛硬币。
  唯一能确定性控制的是后期改 F0 曲线。

方法：
  Praat Manipulation → Extract PitchTier → 逐点按幂律缩放偏离量 → PSOLA 重合成
      f' = med * (f / med) ** alpha
  alpha=0.57 即把起伏压到 57%（马修 5.76 / 我们 10.15）。
  alpha<1 压缩，alpha>1 放大（用于「起伏不足」）。

风险（必须实测，不能假设）：
  PSOLA 会改音色。记忆里 WORLD 合成更差（0.702）、`transients=crisp` 毁起音，
  所以这里必须同时测：span_st 是否到位、声纹是否保持、HNR 是否退化。

用法：
  python mt_pitch_compress.py --in _mt_raw_s42 --out _mt_pc057 --alpha 0.57 --limit 20
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call

sys.path.insert(0, r'G:/_setup')


def compress_once(path, out_path, alpha, floor=60.0, ceil=250.0):
    snd = parselmouth.Sound(path)
    try:
        manip = call(snd, "To Manipulation", 0.01, floor, ceil)
        tier = call(manip, "Extract pitch tier")
    except Exception as e:
        return None, 'manip_fail:%s' % e
    n = call(tier, "Get number of points")
    if n < 3:
        return None, 'too_few_points'
    times = [call(tier, "Get time from index", i + 1) for i in range(n)]
    vals = [call(tier, "Get value at index", i + 1) for i in range(n)]
    fv = np.array(vals, float)
    ok = fv > 0
    if ok.sum() < 3:
        return None, 'no_voiced'
    med = float(np.median(fv[ok]))
    new = fv.copy()
    new[ok] = med * np.power(fv[ok] / med, alpha)
    # 清空后重写（Praat 没有批量 set，只能 remove + add）
    call(tier, "Remove points between", 0.0, 1e9)
    for t, f in zip(times, new):
        if f > 0:
            call(tier, "Add point", float(t), float(f))
    call([manip, tier], "Replace pitch tier")
    res = call(manip, "Get resynthesis (PSOLA)")
    res.save(out_path, "WAV")
    return dict(n_points=int(ok.sum()), med_hz=round(med, 2)), 'ok'


def compress(path, out_path, alpha, times=2, **kw):
    """级联 PSOLA。

    为什么必须级联：
      单次 PSOLA 的实际压缩比不跟 alpha 走 —— alpha 0.57 只到 0.746、
      0.35 只到 0.695、0.15 只到 0.679（颗粒拼接会平滑 F0，且下限 60Hz 兜底）。
      实测单次最低 0.679，**达不到马修需要的 0.57**。
      级联两次 alpha 0.35 → 0.649，音色仍保持（F1-3 不变、MFCC 0.9997）。
      三次反而反弹到 0.685 ⇒ 两次是上限，不要更多。

    为什么不用 pyworld：
      pyworld alpha=0.57 能精确压到 0.565，但 F2 从 1462 变 1739（+19%），
      元音音色被改。PSOLA 的 F1/F2/F3 完全不变。
    """
    cur = path
    info = None
    tmpdir = os.path.dirname(out_path) or '.'
    for k in range(max(1, times)):
        tgt = out_path if k == times - 1 else os.path.join(
            tmpdir, '_tmp_%d_%s' % (k, os.path.basename(out_path)))
        info, st = compress_once(cur, tgt, alpha, **kw)
        if st != 'ok':
            return None, st
        cur = tgt
    # 清理中间文件
    for k in range(max(1, times) - 1):
        p = os.path.join(tmpdir, '_tmp_%d_%s' % (k, os.path.basename(out_path)))
        if os.path.exists(p):
            os.unlink(p)
    return info, 'ok'


def feats(path):
    """段级轮廓特征（与 mt_matt_contour 同口径），返回单元级汇总。"""
    from mt_matt_contour import segs_of, f0_track, shape_feats
    segs, x, sr = segs_of(path)
    out = []
    for a, b in segs:
        tr, st = f0_track(x, sr, a, b)
        if tr is None or len(tr) < 8:
            continue
        f = shape_feats(tr, st)
        f['dur'] = b - a
        out.append(f)
    if not out:
        return None
    return dict(n_seg=len(out),
                iqr=float(np.median([f['iqr_st'] for f in out])),
                span=float(np.median([f['span_st'] for f in out])),
                span_all=float(np.percentile([f['span_st'] for f in out], 90)),
                decl=float(np.median([f['decl_st'] for f in out])),
                npeaks=float(np.median([f['n_peaks'] for f in out])),
                flat_pct=float(np.mean([f['shape'] == 'flat' for f in out])))


def hnr_of(path):
    """HNR 用 librosa 的 HPSS 算（谐波/打击成分能量比）。

    不用 parselmouth 的 To Harmonicity (cc)：实测返回 −127 dB 这种无意义值，
    因为旁白 HNR 只有 −1.9 dB（气声重），该算法在此类素材上失效。
    """
    import librosa
    y, sr = sf.read(path, dtype='float64', always_2d=True)
    y = y.mean(1).astype(np.float32)
    H, P = librosa.effects.hpss(y)
    return float(10 * np.log10((H ** 2).sum() / max(1e-12, (P ** 2).sum())))


def mfcc_cos(p1, p2):
    """用 MFCC 均值向量的余弦相似度近似「音色是否保持」。"""
    import librosa

    def emb(p):
        y, sr = sf.read(p, dtype='float64', always_2d=True)
        y = y.mean(1)
        if len(y) < sr // 10:
            return None
        m = librosa.feature.mfcc(y=y.astype(np.float32), sr=sr, n_mfcc=13,
                                 n_fft=1024, hop_length=256)
        v = m[1:].mean(1)          # 去掉 c0（能量）
        n = np.linalg.norm(v)
        return v / n if n > 0 else None

    a, b = emb(p1), emb(p2)
    if a is None or b is None or a.shape != b.shape:
        return float('nan')
    return float(a @ b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', default=r'G:/_setup/_mt_raw_s42')
    ap.add_argument('--out', dest='outp', default=r'G:/_setup/_mt_pc057')
    ap.add_argument('--alpha', type=float, default=0.35)
    ap.add_argument('--times', type=int, default=2)
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--only', default='', help='逗号分隔的 N 编号，只处理这些')
    ap.add_argument('--json', default=r'G:/_setup/_pitch_compress.json')
    a = ap.parse_args()

    os.makedirs(a.outp, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.inp, '*.wav')))
    if a.only:
        want = set(x.strip() for x in a.only.split(','))
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in want]
    if a.limit:
        files = files[:a.limit]
    print('处理 %d 个，alpha=%.2f ×%d' % (len(files), a.alpha, a.times))

    rows = []
    for i, f in enumerate(files):
        name = os.path.basename(f)
        op = os.path.join(a.outp, name)
        info, st = compress(f, op, a.alpha, a.times)
        if st != 'ok':
            print('  !! %s %s' % (name, st))
            continue
        fa, fb = feats(f), feats(op)
        if fa is None or fb is None:
            print('  !! %s 特征失败' % name)
            continue
        row = dict(name=name, iqr0=round(fa['iqr'], 2), iqr1=round(fb['iqr'], 2),
                   span0=round(fa['span'], 2), span1=round(fb['span'], 2),
                   decl0=round(fa['decl'], 2), decl1=round(fb['decl'], 2),
                   npeaks0=fa['npeaks'], npeaks1=fb['npeaks'],
                   flat0=round(fa['flat_pct'], 2), flat1=round(fb['flat_pct'], 2),
                   hnr0=round(hnr_of(f), 2), hnr1=round(hnr_of(op), 2),
                   mfcc=round(mfcc_cos(f, op), 3), **info)
        rows.append(row)
        if (i + 1) % 5 == 0:
            print('  %d/%d' % (i + 1, len(files)), flush=True)

    if not rows:
        raise SystemExit('全部失败')
    print('\n%-10s %6s %6s %7s %7s %7s %7s %6s' % (
        'name', 'iqr0', 'iqr1', 'span0', 'span1', 'decl0', 'decl1', 'mfcc'))
    for r in rows:
        print('%-10s %6.2f %6.2f %7.2f %7.2f %7.2f %7.2f %6.3f' % (
            r['name'], r['iqr0'], r['iqr1'], r['span0'], r['span1'],
            r['decl0'], r['decl1'], r['mfcc']))

    s0 = np.array([r['iqr0'] for r in rows])
    s1 = np.array([r['iqr1'] for r in rows])
    ratio = np.median(s1 / np.maximum(s0, 1e-6))
    print('\n=== 汇总（n=%d）===' % len(rows))
    print('  IQR 中位 %.2f → %.2f，实际压缩比 %.3f（目标 %.2f）' % (
        np.median(s0), np.median(s1), ratio, a.alpha))
    print('  逐条压缩比 p10 %.2f / p50 %.2f / p90 %.2f' % tuple(
        np.percentile(s1 / np.maximum(s0, 1e-6), [10, 50, 90])))
    print('  反向（变大 >1.05）: %d 条；过度（<0.4）: %d 条' % (
        int((s1 / np.maximum(s0, 1e-6) > 1.05).sum()),
        int((s1 / np.maximum(s0, 1e-6) < 0.4).sum())))
    print('  decl 中位 %+.2f → %+.2f' % (np.median([r['decl0'] for r in rows]),
                                        np.median([r['decl1'] for r in rows])))
    print('  HNR 中位 %.2f → %.2f（Δ %+.2f）' % (
        np.median([r['hnr0'] for r in rows]), np.median([r['hnr1'] for r in rows]),
        np.median([r['hnr1'] for r in rows]) - np.median([r['hnr0'] for r in rows])))
    print('  MFCC 余弦中位 %.3f（p10 %.3f）' % (
        np.median([r['mfcc'] for r in rows]), np.percentile([r['mfcc'] for r in rows], 10)))
    print('  flat 占比 %.2f → %.2f' % (np.median([r['flat0'] for r in rows]),
                                      np.median([r['flat1'] for r in rows])))
    json.dump(dict(alpha=a.alpha, n=len(rows), rows=rows),
              open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→ %s' % a.json)


if __name__ == '__main__':
    main()
