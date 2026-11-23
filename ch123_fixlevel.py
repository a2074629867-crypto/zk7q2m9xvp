# -*- coding: utf-8 -*-
"""短促插话段电平校正。

问题：0.3s 左右的短段（"then?" / "Look,"）生成出来比句子主干高 7-11dB，
      听感是"突然吼一下"。这类段与主干之间有静音，单独调电平最安全。

做法：找 voiced RMS 高于本文件中位 +THRESH 的短段（<0.45s），
      乘增益把它拉到中位，段首尾各 15ms 余弦过渡（避免咔哒）。
      不动长段，保住正常的强弱对比。

用法：python ch123_fixlevel.py L014 L069 ...
"""
import os
import sys
import shutil
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_clean as CL

THRESH = 5.0      # 高于中位多少 dB 才算异常
SHORT = 0.45      # 只处理短于这个时长的段
RAMP = 0.015
DST = "ch123_final"
BACKUP = "ch123_pre_lvl"


def fix(a, sr):
    # 下限放到 0.08s：L087 的 "Look," 只有 0.12s，之前被 0.20s 的门槛漏掉，
    # 它以 +11dB 独立成段，是"突然吼一下"的直接来源。
    segs = [(s0, s1) for s0, s1 in RB.split_at_silence(a, sr, min_gap=0.12)
            if s1 - s0 >= 0.08]
    if len(segs) < 2:
        return a, []
    dbs = [RB.rms_voiced_db(a[int(s0 * sr):int(s1 * sr)], sr) for s0, s1 in segs]
    # 基准取「最长那一段」的电平（句子主干），不用中位——
    # 只有两段时中位会被短段抬高，反而漏判。
    main = int(np.argmax([s1 - s0 for s0, s1 in segs]))
    med = dbs[main]
    y = a.copy()
    log = []
    for (s0, s1), db in zip(segs, dbs):
        if (s1 - s0) > SHORT or db < med + THRESH:
            continue
        g = 10 ** ((med - db) / 20.0)
        i0, i1 = int(s0 * sr), int(s1 * sr)
        n = i1 - i0
        r = max(1, int(RAMP * sr))
        env = np.ones(n, dtype=np.float32)
        env[:r] = 0.5 * (1 - np.cos(np.pi * np.arange(r) / r))
        env[-r:] = 0.5 * (1 + np.cos(np.pi * np.arange(r) / r))
        gain = 1.0 + (g - 1.0) * env
        y[i0:i1] *= gain
        log.append((s0, s1, db, med, 20 * np.log10(g)))
    return y, log


def main():
    keys = sys.argv[1:]
    os.makedirs(BACKUP, exist_ok=True)
    for k in keys:
        p = os.path.join(DST, k + ".wav")
        a, sr = sf.read(p, dtype="float32", always_2d=True)
        a = a.mean(1)
        y, log = fix(a, sr)
        if not log:
            print("%-6s 无需处理" % k)
            continue
        y = CL.clean(y, sr)
        bak = os.path.join(BACKUP, k + ".wav")
        if not os.path.exists(bak):
            shutil.copy2(p, bak)
        sf.write(p, y, sr, subtype="PCM_16")
        for s0, s1, db, med, g in log:
            print("%-6s p@%.2f-%.2f  %.1fdB → 中位 %.1fdB  增益 %+.1fdB"
                  % (k, s0, s1, db, med, g))


if __name__ == "__main__":
    main()
