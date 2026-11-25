# -*- coding: utf-8 -*-
"""
可比性校正：真人录音 vs TTS 输出的 F0 描述量，能不能直接比？

问题：真人有底噪、连读、气声，F0 检测器更保守（有声帧占比 0.54 vs 我们 0.42）。
      直接比「跨度 4.7st vs 8.9st」会把检测器偏差当成韵律差异。

做法（文献标准：协变量匹配 / propensity matching）：
  1. 每句算「有声帧占比」作为检测器可见度的代理
  2. 只在两边各自的有声帧占比**重叠区间**内比较（common support）
  3. 再按占比分箱做分层比较，看差异是否随占比消失

另外做一个化验：给 TTS 音频加真人同等水平的底噪，重测，看量变多少。
"""
import json, glob, os, sys
import numpy as np, soundfile as sf, parselmouth

DOC = 'G:/_setup'


def f0_stats(path, floor=60, ceil=350, step=0.01):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1:
        y = y.mean(1)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    p = snd.to_pitch(time_step=step, pitch_floor=floor, pitch_ceiling=ceil)
    f0 = p.selected_array['frequency'].astype(float)
    v = f0 > 0
    if v.sum() < 20:
        return None
    st = 12 * np.log2(f0[v] / 100.0)
    # 底噪：帧能量的 p10
    hop = int(sr * step)
    n = len(y) // hop
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    noise = float(np.percentile(20 * np.log10(e), 10))
    return dict(vr=float(v.mean()), span=float(np.percentile(st, 95) - np.percentile(st, 5)),
                dur=float(len(y) / sr), noise=noise)


def collect(tag, paths):
    out = {}
    for p in paths:
        r = f0_stats(p)
        if r:
            out[os.path.basename(p)[:-4]] = r
    print(f'{tag}: {len(out)}/{len(paths)} 条')
    return out


def main():
    ids = set(l.strip() for l in open(f'{DOC}/_narr_ids716.json', encoding='utf-8')
              .read().strip('[]\n ').replace('"', '').split(',') if l.strip())
    human = collect('human', sorted(glob.glob('E:/ttsds/data/ref_human/*.wav')))
    old = collect('old', [p for p in sorted(glob.glob(f'{DOC}/_audio_ch123/out/*.wav'))
                          if os.path.basename(p)[:-4] in ids])
    new = collect('new', [p for p in sorted(glob.glob(f'{DOC}/_regen_final/*.wav'))
                          if os.path.basename(p)[:-4] in ids])
    json.dump(dict(human=human, old=old, new=new),
              open(f'{DOC}/_match_band.json', 'w', encoding='utf-8'), ensure_ascii=False)

    def arr(d, k):
        return np.array([v[k] for v in d.values()], float)

    print('\n=== 1) 未校正')
    for tag, d in (('human', human), ('old', old), ('new', new)):
        vr, sp, nz = arr(d, 'vr'), arr(d, 'span'), arr(d, 'noise')
        print(f'{tag:6s} n={len(d):4d}  有声帧占比 {np.median(vr):.2f}  '
              f'F0跨度 {np.median(sp):.1f}st  底噪 {np.median(nz):.1f}dBFS')

    # 共同支撑区间
    lo = max(np.percentile(arr(d, 'vr'), 5) for d in (human, old, new))
    hi = min(np.percentile(arr(d, 'vr'), 95) for d in (human, old, new))
    print(f'\n共同支撑区间 有声帧占比 [{lo:.2f}, {hi:.2f}]')

    print('\n=== 2) 只在共同支撑内比较')
    for tag, d in (('human', human), ('old', old), ('new', new)):
        v = arr(d, 'vr'); s = arr(d, 'span')
        m = (v >= lo) & (v <= hi)
        print(f'{tag:6s} n={m.sum():4d}  F0跨度中位 {np.median(s[m]):.1f}st  '
              f'p25/75 {np.percentile(s[m],25):.1f}/{np.percentile(s[m],75):.1f}')

    print('\n=== 3) 按有声帧占比分箱（每箱内真人 vs 新版）')
    edges = np.linspace(lo, hi, 5)
    for i in range(4):
        a, b = edges[i], edges[i + 1]
        row = []
        for tag, d in (('human', human), ('new', new)):
            v = arr(d, 'vr'); s = arr(d, 'span')
            m = (v >= a) & (v < b)
            row.append(f'{tag} n={m.sum():3d} span={np.median(s[m]):.1f}' if m.sum() >= 5 else f'{tag} n={m.sum():3d} —')
        print(f'  vr∈[{a:.2f},{b:.2f})  ' + '   '.join(row))


if __name__ == '__main__':
    main()
