# -*- coding: utf-8 -*-
"""静音段噪声门 v2：按 split_at_silence 的段边界清零段外区域，段内一个采样不碰。

依据：L090 底噪 -120dB（数字静音）→ DIS 4.65 / MOS 4.79（全库最高）；
      L071 底噪 -43.7dB → DIS 1.84 / MOS 1.46（全库最低）。
"""
import sys, os
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_clean as CL

SR = 48000
PAD = 0.030      # 段外保留 30ms，护住起音/尾音
RAMP = 0.010     # 边界 10ms 余弦过渡


def gate_segments(a, sr, pad=PAD, ramp=RAMP, min_gap=0.06):
    segs = [(s0, s1) for s0, s1 in RB.split_at_silence(a, sr, min_gap=min_gap)
            if s1 - s0 >= 0.05]
    y = np.zeros_like(a)
    for s0, s1 in segs:
        i0 = max(0, int((s0 - pad) * sr))
        i1 = min(len(a), int((s1 + pad) * sr))
        y[i0:i1] = a[i0:i1]
    # 每个保留块的边界做余弦过渡（块外是零，所以只衰减内侧）
    k = int(ramp * sr)
    if k > 0:
        t = np.linspace(0, 1, k)
        rise = (0.5 - 0.5 * np.cos(np.pi * t)).astype(np.float32)
        fall = rise[::-1].copy()
        edges = []
        for s0, s1 in segs:
            edges.append((max(0, int((s0 - pad) * sr)), min(len(a), int((s1 + pad) * sr))))
        edges.sort()
        merged = []
        for i0, i1 in edges:
            if merged and i0 <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], i1))
            else:
                merged.append((i0, i1))
        for i0, i1 in merged:
            kk = min(k, (i1 - i0) // 2)
            if kk > 0:
                y[i0:i0 + kk] *= rise[:kk]
                y[i1 - kk:i1] *= fall[-kk:]
    return y, segs


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "ch123_final"
    dst_dir = sys.argv[2] if len(sys.argv) > 2 else "ch123_gate"
    keys = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    os.makedirs(dst_dir, exist_ok=True)

    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".wav"))
    if keys:
        files = [f for f in files if f[:-4] in keys]

    for f in files:
        a, sr = sf.read(os.path.join(src_dir, f), dtype="float32", always_2d=True)
        a = a.mean(1)
        y, segs = gate_segments(a, sr)
        y = CL.clean(y, sr)
        sf.write(os.path.join(dst_dir, f), y, sr, subtype="PCM_16")

        def noise_db(x):
            m = np.ones(len(x), bool)
            for s0, s1 in segs:
                m[int(s0 * sr):int(s1 * sr)] = False
            idx = np.where(m)[0]
            idx = idx[(idx > int(0.05 * sr)) & (idx < len(x) - int(0.05 * sr))]
            return 20 * np.log10(np.sqrt((x[idx] ** 2).mean()) + 1e-12) if len(idx) > 100 else -120

        print("%-6s %.2fs  segs=%d  底噪 %.1f → %.1f dB  peak %.3f"
              % (f[:-4], len(y) / sr, len(segs), noise_db(a), noise_db(y),
                 np.abs(y).max()), flush=True)


if __name__ == "__main__":
    main()
