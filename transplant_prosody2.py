# -*- coding: utf-8 -*-
"""韵律移植 v2：词级对齐版

v1 的问题：整段按比例映射 → 生成端/原声的停顿位置不同时，急剧的音高起伏被平均掉。
v2：用 faster-whisper 拿两边的**词级时间戳**（同一句话，词数一致），
    逐词把 donor 的轮廓重采样到 receiver 的词时间轴上；时长也逐词移植（只搬"相对模式"，不搬整体语速）。

用法:
  python -u transplant_prosody2.py --recv gen.wav --donor real.wav --out out.wav \
      --alpha 1.0 --gain 1.0 --dur-strength 1.0 --final-len 1.2
"""
import argparse
import os
import sys

import numpy as np
import parselmouth
from parselmouth import praat

FLOOR, CEIL = 55.0, 400.0
_WHISPER = None


def get_whisper():
    global _WHISPER
    if _WHISPER is None:
        os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel('small.en', device='cpu', compute_type='int8',
                                cpu_threads=8)
    return _WHISPER


def word_times(wav):
    m = get_whisper()
    segs, _ = m.transcribe(wav, language='en', beam_size=5, word_timestamps=True,
                           vad_filter=False, condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                out.append((float(w.start), float(w.end), t))
    return out


def f0_points(wav, floor=FLOOR, ceil=CEIL, step=0.01, max_dev_st=7.0):
    snd = parselmouth.Sound(wav)
    pitch = snd.to_pitch_ac(time_step=step, pitch_floor=floor, pitch_ceiling=ceil,
                            voicing_threshold=0.35, octave_jump_cost=1.0, octave_cost=0.01)
    f0 = np.asarray(pitch.selected_array['frequency'], dtype=np.float64)
    t = np.asarray(pitch.xs(), dtype=np.float64)
    v = f0 > 0
    tv, fv = t[v], f0[v]
    if len(fv) < 8:
        return tv, fv
    for _ in range(2):
        med = float(np.median(fv))
        keep = np.abs(12.0 * np.log2(fv / med)) <= max_dev_st
        if keep.sum() < 8:
            break
        tv, fv = tv[keep], fv[keep]
    return tv, fv


def norm_contour(tv, fv):
    med = float(np.median(fv))
    st = 12.0 * np.log2(fv / med)
    span = tv[-1] - tv[0]
    u = (tv - tv[0]) / span if span > 1e-6 else np.zeros_like(tv)
    return u, st, med


def build_target_prop(recv, donor, alpha, gain):
    rt, rf = recv
    ru, r_st, r_med = norm_contour(rt, rf)
    if donor is not None and len(donor[1]) >= 8:
        du, d_st, _ = norm_contour(*donor)
        tgt = (1 - alpha) * r_st + alpha * np.interp(ru, du, d_st)
    else:
        tgt = r_st.copy()
    return rt, r_med * np.power(2.0, tgt * gain / 12.0), r_med


def build_target_word(recv, donor, rw, dw, alpha, gain, min_frames=3):
    """逐词把 donor 轮廓映射到 receiver 的词时间轴。"""
    rt, rf = recv
    dt, df = donor
    r_med = float(np.median(rf))
    d_med = float(np.median(df))
    new_f = rf.copy()
    hit = 0
    for (rs, re_, _), (ds, de, _) in zip(rw, dw):
        rm = (rt >= rs - 0.01) & (rt <= re_ + 0.01)
        dm = (dt >= ds - 0.01) & (dt <= de + 0.01)
        if rm.sum() < min_frames or dm.sum() < min_frames:
            continue
        d_st = 12.0 * np.log2(df[dm] / d_med)
        du = (dt[dm] - dt[dm][0]) / max(dt[dm][-1] - dt[dm][0], 1e-6)
        ru = (rt[rm] - rt[rm][0]) / max(rt[rm][-1] - rt[rm][0], 1e-6)
        d_on_r = np.interp(ru, du, d_st)
        r_st = 12.0 * np.log2(rf[rm] / r_med)
        tgt = (1 - alpha) * r_st + alpha * d_on_r
        new_f[rm] = r_med * np.power(2.0, tgt * gain / 12.0)
        hit += 1
    return rt, new_f, r_med, hit


def word_dur_points(rw, dw, strength=1.0, lo=0.6, hi=1.8):
    """逐词时长比例（先除掉整体语速差，只搬相对模式）。"""
    raw = []
    for (rs, re_, _), (ds, de, _) in zip(rw, dw):
        rd, dd = re_ - rs, de - ds
        if rd > 0.05 and dd > 0.05:
            raw.append(((rs + re_) / 2.0, dd / rd))
    if len(raw) < 3:
        return []
    med = float(np.median([r for _, r in raw]))
    out = [(t, float(np.clip((r / med) ** strength, lo, hi))) for t, r in raw]
    return out


def write_pitchtier(path, times, freqs):
    xmax = float(max(times[-1], 1.0)) + 0.1
    lines = ['File type = "ooTextFile"', 'Object class = "PitchTier"', '',
             '0.000000', '%.6f' % xmax, str(len(times))]
    for t, f in zip(times, freqs):
        lines += ['%.6f' % t, '%.4f' % f]
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def write_durationtier(path, points, xmax):
    lines = ['File type = "ooTextFile"', 'Object class = "DurationTier"', '',
             '0.0', '%.6f' % (xmax + 0.1), str(len(points))]
    for t, r in points:
        lines += ['%.6f' % t, '%.4f' % r]
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def resynth(recv_wav, out_wav, pt_path, dt_path=None, floor=FLOOR, ceil=CEIL):
    L = ['sound = Read from file: "%s"' % recv_wav.replace('\\', '/'),
         'manipulation = To Manipulation: 0.01, %g, %g' % (floor, ceil),
         'pitchTier = Read from file: "%s"' % pt_path.replace('\\', '/'),
         'selectObject: manipulation, pitchTier', 'Replace pitch tier']
    if dt_path:
        L += ['durationTier = Read from file: "%s"' % dt_path.replace('\\', '/'),
              'selectObject: manipulation, durationTier', 'Replace duration tier']
    L += ['selectObject: manipulation', 'resynth = Get resynthesis (overlap-add)',
          'Write to WAV file: "%s"' % out_wav.replace('\\', '/')]
    praat.run('\n'.join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recv', required=True)
    ap.add_argument('--donor', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--alpha', type=float, default=1.0)
    ap.add_argument('--gain', type=float, default=1.0)
    ap.add_argument('--align', default='word', choices=['word', 'prop'])
    ap.add_argument('--dur-strength', type=float, default=0.0)
    ap.add_argument('--final-len', type=float, default=1.0)
    ap.add_argument('--no-dur', action='store_true')
    a = ap.parse_args()

    work = os.path.dirname(os.path.abspath(a.out)) or '.'
    os.makedirs(work, exist_ok=True)
    base = os.path.splitext(os.path.basename(a.out))[0]

    recv = f0_points(a.recv)
    donor = f0_points(a.donor) if a.donor else None
    if len(recv[1]) < 8:
        raise SystemExit('receiver 浊音帧太少: ' + a.recv)

    mode = a.align
    hit = 0
    if mode == 'word' and donor is not None:
        rw, dw = word_times(a.recv), word_times(a.donor)
        if len(rw) == len(dw) and len(rw) >= 3:
            rt, f_new, med, hit = build_target_word(recv, donor, rw, dw, a.alpha, a.gain)
        else:
            print('[warn] 词数不一致 (%d vs %d)，退回比例对齐' % (len(rw), len(dw)))
            rt, f_new, med = build_target_prop(recv, donor, a.alpha, a.gain)
            mode = 'prop'
            rw = dw = None
    else:
        rt, f_new, med = build_target_prop(recv, donor, a.alpha, a.gain)
        rw = dw = None

    pt = os.path.join(work, base + '.PitchTier')
    write_pitchtier(pt, rt, f_new)

    dtp = None
    pts = []
    if not a.no_dur:
        if rw and dw and a.dur_strength > 0:
            pts += word_dur_points(rw, dw, a.dur_strength)
        if a.final_len != 1.0:
            d = float(parselmouth.Sound(a.recv).duration)
            pts += [(d * 0.82, 1.0), (d * 0.995, a.final_len)]
        if pts:
            pts.sort()
            dtp = os.path.join(work, base + '.DurationTier')
            write_durationtier(dtp, pts, float(parselmouth.Sound(a.recv).duration))

    resynth(a.recv, a.out, pt, dtp)
    for p in (pt, dtp):
        if p and os.path.exists(p):
            os.remove(p)

    st = 12.0 * np.log2(f_new / med)
    print('[ok] %-26s %s α=%.2f gain=%.2f 词命中%d  跨度%.2f半音  时长→%.2fs' %
          (os.path.basename(a.recv), mode, a.alpha, a.gain, hit,
           float(np.percentile(st, 95) - np.percentile(st, 5)),
           parselmouth.Sound(a.out).duration), flush=True)


if __name__ == '__main__':
    main()
