# -*- coding: utf-8 -*-
"""韵律移植：把真实录音的「句级音调弧线 + 时长模式」搬到 GPT-SoVITS 生成音频上。

核心思路（比 ProMo 的 min/max 归一化更抗离群点）：
  1. 两边都在 **半音空间、以各自中位数为基准** 表示轮廓 → 去掉绝对音高差
  2. 时间归一化到 [0,1]，把 donor 的轮廓重采样到 receiver 的时间轴
  3. target_st(t) = (1-α)·recv_st(t) + α·donor_st(t)      α=混合强度
     再乘 gain 做额外夸张： target_st *= gain
  4. 回到 Hz 时用 **receiver 自己的中位数** → 保持本人音区不变
  5. 用 parselmouth(Praat) 的 Manipulation 重合成（PitchTier + DurationTier）

时长侧：
  - --final-len   句末 N% 的延长倍率（oratory 的句末拖长）
  - --pause-len   段内停顿的延长倍率（演讲式停顿）
  - --word-ratio  按词级 TextGrid 移植时长比例（可选）

用法:
  python -u transplant_prosody.py --recv gen.wav --donor real.wav --out out.wav \
      --alpha 0.7 --gain 1.0 --final-len 1.2
"""
import argparse
import os

import numpy as np
import parselmouth
from parselmouth import praat

FLOOR, CEIL = 55.0, 400.0


# ---------------- F0 提取（带离群点剔除） ----------------
def f0_points(wav, floor=FLOOR, ceil=CEIL, step=0.01, max_dev_st=7.0):
    """返回 (times, freqs) —— 仅浊音帧，且已剔除倍频/半频离群点。"""
    snd = parselmouth.Sound(wav)
    pitch = snd.to_pitch_ac(time_step=step, pitch_floor=floor, pitch_ceiling=ceil,
                            voicing_threshold=0.35, octave_jump_cost=1.0,
                            octave_cost=0.01)
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
    """→ (相对时间[0,1], 半音轮廓)"""
    med = float(np.median(fv))
    st = 12.0 * np.log2(fv / med)
    span = tv[-1] - tv[0]
    u = (tv - tv[0]) / span if span > 1e-6 else np.zeros_like(tv)
    return u, st, med


# ---------------- 目标轮廓 ----------------
def build_target(recv, donor, alpha=0.7, gain=1.0, smooth_ms=0.0):
    """recv/donor = (times, freqs)。返回 (recv_times, 新频率数组)。"""
    rt, rf = recv
    ru, r_st, r_med = norm_contour(rt, rf)
    if donor is not None and len(donor[1]) >= 8:
        dt, df = donor
        du, d_st, _ = norm_contour(dt, df)
        # 把 donor 轮廓重采样到 receiver 的相对时间轴
        d_on_r = np.interp(ru, du, d_st)
        tgt = (1.0 - alpha) * r_st + alpha * d_on_r
    else:
        tgt = r_st.copy()
    tgt = tgt * gain
    if smooth_ms > 0:
        k = max(1, int(smooth_ms / 10.0))
        if k > 1:
            ker = np.ones(k) / k
            tgt = np.convolve(np.pad(tgt, (k // 2, k - 1 - k // 2), mode='edge'),
                              ker, mode='valid')
    f_new = r_med * np.power(2.0, tgt / 12.0)
    return rt, f_new, r_med


# ---------------- Praat 文件写出 ----------------
def write_pitchtier(path, times, freqs):
    xmin = 0.0
    xmax = float(max(times[-1], 1.0)) + 0.1
    lines = ['File type = "ooTextFile"', 'Object class = "PitchTier"', '',
             '%.6f' % xmin, '%.6f' % xmax, str(len(times))]
    for t, f in zip(times, freqs):
        lines.append('%.6f' % t)
        lines.append('%.4f' % f)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def write_durationtier(path, points, xmax):
    lines = ['File type = "ooTextFile"', 'Object class = "DurationTier"', '',
             '0.0', '%.6f' % (xmax + 0.1), str(len(points))]
    for t, r in points:
        lines.append('%.6f' % t)
        lines.append('%.4f' % r)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


# ---------------- 重合成 ----------------
def resynth(recv_wav, out_wav, pt_path, dt_path=None, floor=FLOOR, ceil=CEIL):
    lines = [
        'sound = Read from file: "%s"' % recv_wav.replace('\\', '/'),
        'manipulation = To Manipulation: 0.01, %g, %g' % (floor, ceil),
        'pitchTier = Read from file: "%s"' % pt_path.replace('\\', '/'),
        'selectObject: manipulation, pitchTier',
        'Replace pitch tier',
    ]
    if dt_path:
        lines += [
            'durationTier = Read from file: "%s"' % dt_path.replace('\\', '/'),
            'selectObject: manipulation, durationTier',
            'Replace duration tier',
        ]
    lines += [
        'selectObject: manipulation',
        'resynth = Get resynthesis (overlap-add)',
        'Write to WAV file: "%s"' % out_wav.replace('\\', '/'),
    ]
    praat.run('\n'.join(lines))


# ---------------- 时长点 ----------------
def duration_points(recv_wav, final_len=1.0, pause_len=1.0, word_pairs=None,
                    final_frac=0.82):
    """构造 DurationTier 点 [(time, ratio)]。
    word_pairs: [(t_mid, ratio), ...] 词级比例（可选，优先级最高）。"""
    snd = parselmouth.Sound(recv_wav)
    dur = float(snd.duration)
    pts = []
    if word_pairs:
        pts += word_pairs
    if final_len != 1.0:
        pts += [(dur * final_frac, 1.0), (dur * 0.995, final_len)]
    if pause_len != 1.0:
        # 找内部静音段并延长
        inten = snd.to_intensity(minimum_pitch=100.0, time_step=0.01)
        vals = np.asarray(inten.values).ravel()
        ts = np.asarray(inten.xs())
        if len(vals) > 4:
            thr = max(1e-6, float(np.percentile(vals, 10)) + 6.0)
            quiet = vals < thr
            i = 0
            while i < len(quiet):
                if quiet[i]:
                    j = i
                    while j < len(quiet) and quiet[j]:
                        j += 1
                    t0, t1 = ts[i], ts[j - 1]
                    if 0.08 <= (t1 - t0) <= 1.2 and t0 > 0.05 and t1 < dur - 0.05:
                        pts.append(((t0 + t1) / 2.0, pause_len))
                    i = j
                else:
                    i += 1
    if not pts:
        return None
    pts.sort()
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recv', required=True)
    ap.add_argument('--donor', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--alpha', type=float, default=0.7, help='轮廓移植强度 0~1')
    ap.add_argument('--gain', type=float, default=1.0, help='额外夸张倍率')
    ap.add_argument('--smooth-ms', type=float, default=0.0)
    ap.add_argument('--final-len', type=float, default=1.0)
    ap.add_argument('--pause-len', type=float, default=1.0)
    ap.add_argument('--keep-pt', action='store_true', help='保留中间文件')
    a = ap.parse_args()

    work = os.path.dirname(os.path.abspath(a.out)) or '.'
    os.makedirs(work, exist_ok=True)
    base = os.path.splitext(os.path.basename(a.out))[0]

    recv = f0_points(a.recv)
    donor = f0_points(a.donor) if a.donor else None
    if len(recv[1]) < 8:
        raise SystemExit('receiver 浊音帧太少，无法处理: ' + a.recv)

    rt, f_new, med = build_target(recv, donor, a.alpha, a.gain, a.smooth_ms)

    pt_path = os.path.join(work, base + '.PitchTier')
    write_pitchtier(pt_path, rt, f_new)

    dt_path = None
    pts = duration_points(a.recv, a.final_len, a.pause_len)
    if pts:
        dt_path = os.path.join(work, base + '.DurationTier')
        write_durationtier(dt_path, pts, float(parselmouth.Sound(a.recv).duration))

    resynth(a.recv, a.out, pt_path, dt_path)

    if not a.keep_pt:
        for p in (pt_path, dt_path):
            if p and os.path.exists(p):
                os.remove(p)

    st = 12.0 * np.log2(f_new / med)
    print('[ok] %-28s α=%.2f gain=%.2f  轮廓跨度%.2f半音  中位%.1fHz -> %s' %
          (os.path.basename(a.recv), a.alpha, a.gain,
           float(np.percentile(st, 95) - np.percentile(st, 5)), med,
           os.path.basename(a.out)), flush=True)


if __name__ == '__main__':
    main()
