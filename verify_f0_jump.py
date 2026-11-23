# -*- coding: utf-8 -*-
"""验证旁白 196 条 F0 突跳 FIX 是真是假。

假设：parselmouth 在气声/低音上抓错基频（2× 或 3× 基频），产出的"突跳"不是语调跳变。
验证：对同一批音频换三组 pitch 参数重测，看突跳次数是否随 ceiling 收紧而消失。
  A 组 = narr_check 现行参数 floor60 / ceil250 / vt0.20
  B 组 = 男低音收紧 floor60 / ceil160 / vt0.30
  C 组 = 更严 voicing floor60 / ceil160 / vt0.45
判据：若 A 有突跳而 B/C 大幅减少 ⇒ 跟踪错误（假 FIX）。
     若三组都保留突跳 ⇒ 真实语调跳变（真 FIX）。
"""
import json
import random

import numpy as np
import parselmouth
import soundfile as sf

SRC = "G:/_setup/_narr_check2/_narr_check.json"
ADIR = "G:/_setup/_audio_ch123/out/"
N = 30
random.seed(7)


def jumps(path, floor, ceil, vt):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    x = np.ascontiguousarray(x, dtype=np.float64)
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                        voicing_threshold=vt, silence_threshold=0.03)
    f = np.asarray(p.selected_array["frequency"], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    v = f > 0
    if v.sum() < 8:
        return 0, 0.0, 0.0
    st = 12 * np.log2(np.maximum(f, 1e-6) / 100.0)
    ev, mx = [], 0.0
    for i in range(1, len(f)):
        if v[i] and v[i - 1] and abs(t[i] - t[i - 1]) < 0.03:
            dd = abs(st[i] - st[i - 1])
            if 10.5 <= dd <= 13.5:
                continue          # 八度错误，narr_check 已归 WATCH
            if dd > 9.0:
                ev.append(t[i])
                mx = max(mx, dd)
    n, last = 0, -9.0
    for tt in ev:
        if tt - last > 0.08:
            n += 1
        last = tt
    fv = f[v]
    return n, mx, float(np.median(fv))


rows = json.load(open(SRC, encoding="utf-8"))
fix = [r for r in rows if r["verdict"] == "FIX"]
print("FIX 总数 %d，其中 F0 突跳 %d" % (len(fix), sum(1 for r in fix if r.get("f0_jump_fix"))))

pool = [r for r in fix if r.get("f0_jump_fix")]
sample = random.sample(pool, min(N, len(pool)))
print("抽样 %d 条，三组参数重测：\n" % len(sample))
print("%-10s %5s | %-18s | %-18s | %-18s" % ("id", "dur", "A 60/250/0.20", "B 60/160/0.30", "C 60/160/0.45"))
keepA = keepB = keepC = 0
for r in sample:
    p = ADIR + r["unit"] + ".wav"
    try:
        a = jumps(p, 60, 250, 0.20)
        b = jumps(p, 60, 160, 0.30)
        c = jumps(p, 60, 160, 0.45)
    except Exception as e:
        print("%-10s  ERR %s" % (r["unit"], e))
        continue
    keepA += a[0] >= 2
    keepB += b[0] >= 2
    keepC += c[0] >= 2
    print("%-10s %5.1f | n=%d max=%4.1f f0=%5.1f | n=%d max=%4.1f f0=%5.1f | n=%d max=%4.1f f0=%5.1f"
          % (r["unit"], r.get("dur") or 0,
             a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]))

print("\n仍判 FIX(>=2 次突跳)：A %d / %d ｜ B %d / %d ｜ C %d / %d"
      % (keepA, len(sample), keepB, len(sample), keepC, len(sample)))
