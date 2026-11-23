# -*- coding: utf-8 -*-
"""标点表达度检测：这个逗号，TTS 到底念出来了没有？

为什么必须单独测
  事后插停顿只能补「静音」。一个真正被读出来的逗号同时带着三样东西：
    ① 边界前延长（pre-boundary lengthening）
    ② 音高重置 / 下降（pitch reset）
    ③ 能量下凹（intensity dip）
  TTS 如果把逗号吞了，它连 ①②③ 一起没有 —— 这时候只塞一段静音，
  听感是「话说完了 → 空白 → 接着说」，而不是「一句话里的换气」。

判据（三项独立测，不合并成单分）
  gap        = 后词起点 − 前词终点
  pre_ratio  = 前词时长 / 全句词时长中位      （>1.25 算延长）
  f0_st      = 后词首窗 F0 中位 − 前词末窗 F0 中位，半音（负值=下沉，正值=重置）
  dip_db     = 边界处最小帧能量 − 前词主体中位能量

分级
  strong  停顿已经念出来（gap ≥ 0.30）
  weak    有边界迹象但停顿不足（gap ≥ 0.06，或有延长/音高变化）
  none    **逗号被吞**（gap < 0.06 且无延长、无音高变化）→ 该进重生成清单，不该靠后期硬塞

用法
  python -u mt_punct_expr.py --only L005,L046,L084,L087
  python -u mt_punct_expr.py                 # 全库，出 _punct_expr.json
"""
import argparse
import glob
import json
import os
import sys

os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
sys.path.insert(0, r'G:/_setup')

import numpy as np
import parselmouth
import soundfile as sf

from _wtlib import word_times_cached as word_times
from mt_final_pause import frame_db
from mt_pause_rules import _norm, _strong, align_pair, parse_text, segments

GAP_STRONG = 0.30
GAP_WEAK = 0.06
PRE_RATIO = 1.25
F0_ST = 1.5


def pitch_contour(snd):
    """整句 F0 轮廓一次算完，后面按时间查；避免每处边界重复 extract_part。"""
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=320,
                        voicing_threshold=0.20, silence_threshold=0.03)
    f = np.asarray(p.selected_array['frequency'], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    return t, f


def f0_at(t, f, a, b, max_ext=0.40):
    """[a,b] 内的浊音中位；取不到就向两侧逐级扩窗（清音边界处很常见）。"""
    step = 0.10
    for ext in (0.0, step, 2 * step, 3 * step, max_ext):
        a2, b2 = a - ext, b + ext
        m = (t >= a2) & (t <= b2) & (f > 0)
        if m.sum() >= 3:
            return float(np.median(f[m]))
    return float('nan')


def expr_of(wav, text):
    rw = word_times(wav)
    toks = parse_text(text)
    if len(rw) < 2 or len(toks) < 2:
        return [], rw, toks

    x, sr = sf.read(wav, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    db, nf, hf = frame_db(x, sr, fl=0.02, hop=0.01)
    snd = parselmouth.Sound(np.ascontiguousarray(x), sampling_frequency=sr)
    tF, fF = pitch_contour(snd)

    durs = [b - a for a, b, _ in rw]
    med_dur = float(np.median(durs))

    a = [_norm(w) for w, _ in toks]
    b = [_norm(w[2]) for w in rw]
    pair = align_pair(a, b)
    rows = []
    for i in range(len(toks) - 1):
        p = toks[i][1]
        if not p or not (set(p) & set(',;:.?!')):
            continue
        if i not in pair or (i + 1) not in pair:
            rows.append(dict(i=i, word=toks[i][0], punct=p, status='unaligned'))
            continue
        ia, ib = pair[i], pair[i + 1]
        end, nxt = rw[ia][1], rw[ib][0]
        gap = max(nxt - end, 0.0)
        pre = rw[ia][1] - rw[ia][0]
        pre_ratio = pre / med_dur if med_dur > 1e-6 else 1.0

        f_pre = f0_at(tF, fF, end - 0.15, end)
        f_post = f0_at(tF, fF, nxt, nxt + 0.15)
        if np.isnan(f_pre) or np.isnan(f_post) or f_pre <= 0 or f_post <= 0:
            f0_st = None
        else:
            f0_st = round(float(12.0 * np.log2(f_post / f_pre)), 2)

        a0 = max(0, int((end - 0.03) * sr / hf))
        a1 = min(len(db), int((nxt + 0.03) * sr / hf) + 1)
        seg = db[a0:a1] if a1 > a0 else np.array([0.0])
        has_zero = bool((seg < -90).any())
        voiced_seg = seg[seg > -90]
        ref = np.median(db[max(0, a0 - 8):a0 + 1])
        dip = round(float(voiced_seg.min() - ref), 1) if len(voiced_seg) else None

        has_len = pre_ratio >= PRE_RATIO
        has_f0 = f0_st is not None and abs(f0_st) >= F0_ST
        if gap >= GAP_STRONG:
            verdict = 'strong'
        elif gap >= GAP_WEAK:
            verdict = 'weak'
        elif has_len or has_f0:
            verdict = 'weak'      # 停顿没有，但有延长或音高变化 → 半表达
        else:
            verdict = 'none'      # 完全吞掉

        rows.append(dict(i=i, word=toks[i][0], punct=p, status=verdict,
                         gap=round(gap, 3), pre_ratio=round(pre_ratio, 2),
                         f0_st=f0_st, dip_db=dip, has_zero=has_zero,
                         has_len=bool(has_len), has_f0=bool(has_f0),
                         need=round(max(0.0, 1.16 - gap), 2)))
    return rows, rw, toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=r'G:/_setup/ch123_final')
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default=r'G:/_setup/_punct_expr.json')
    a = ap.parse_args()

    from ch123_plan import INNER, PLAN
    TEXT = {'L%03d' % i: t for i, _, _, t in PLAN}
    TEXT.update({'I%02d' % i: t for i, (_, _, _, t) in enumerate(INNER)})

    files = sorted(glob.glob(os.path.join(a.dir, '*.wav')))
    if a.only:
        keep = set(a.only.split(','))
        files = [f for f in files if os.path.basename(f)[:-4] in keep]

    all_rows = {}
    for f in files:
        k = os.path.basename(f)[:-4]
        if k not in TEXT:
            continue
        rows, rw, toks = expr_of(f, TEXT[k])
        all_rows[k] = rows
        cnt = {}
        for r in rows:
            cnt[r['status']] = cnt.get(r['status'], 0) + 1
        print('%-5s %s' % (k, '  '.join('%s=%d' % (s, cnt.get(s, 0))
                                        for s in ('strong', 'weak', 'none', 'unaligned'))))
        for r in rows:
            if r['status'] == 'unaligned':
                print('        %-14s [%s] 对齐失败' % (r['word'] + r['punct'], r['punct']))
                continue
            tag = 'silent' if r['has_zero'] else (
                '%.1fdB' % r['dip_db'] if r['dip_db'] is not None else 'n/a')
            print('        %-14s %-7s gap %.3fs  延长 %.2fx  F0 %6s  下凹 %-8s %s'
                  % (r['word'] + r['punct'], r['status'], r['gap'], r['pre_ratio'],
                     '%+.1fst' % r['f0_st'] if r['f0_st'] is not None else 'n/a',
                     tag,
                     ('延长' if r['has_len'] else '') + ('音高' if r['has_f0'] else '')))

    json.dump(all_rows, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    tot = {'strong': 0, 'weak': 0, 'none': 0, 'unaligned': 0}
    gaps = []
    for rows in all_rows.values():
        for r in rows:
            tot[r['status']] = tot.get(r['status'], 0) + 1
            if r['status'] != 'unaligned':
                gaps.append(r['gap'])
    print('\n===== 汇总 =====')
    n = sum(tot.values())
    print('标点位置 %d 处：strong %d (%.0f%%)  weak %d (%.0f%%)  none %d (%.0f%%)  unaligned %d'
          % (n, tot['strong'], 100 * tot['strong'] / n, tot['weak'], 100 * tot['weak'] / n,
             tot['none'], 100 * tot['none'] / n, tot['unaligned']))
    if gaps:
        g = np.array(gaps)
        print('现有 gap：中位 %.3fs  p25 %.3f  p75 %.3f  max %.3f  <0.06s 的有 %d 处'
              % (np.median(g), np.percentile(g, 25), np.percentile(g, 75), g.max(),
                 int((g < GAP_WEAK).sum())))
    print('报告: %s' % a.out)

    # 需要重生成的条目：有标点完全没被表达出来的，优先于后期硬塞
    regen = []
    for k, rows in all_rows.items():
        bad = [r for r in rows if r['status'] in ('none', 'unaligned')]
        if bad:
            regen.append(dict(key=k, n=len(bad),
                              items=['%s%s%s' % (r['word'], r['punct'],
                                                 ('(%.3fs)' % r['gap']) if 'gap' in r else '(未对齐)')
                                     for r in bad]))
    regen.sort(key=lambda x: -x['n'])
    if regen:
        print('\n标点完全没表达的条目 %d 条（建议进重生成清单，不是后期硬塞）：' % len(regen))
        for r in regen:
            print('  %-5s %s' % (r['key'], ' '.join(r['items'])))
        json.dump(regen, open(a.out.replace('.json', '_regen.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
