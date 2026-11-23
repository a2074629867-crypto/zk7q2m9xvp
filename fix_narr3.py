# -*- coding: utf-8 -*-
"""fix_narr3.py —— 旁白 3 条 FIX 的本地修复（不重生成、不用 GPU）。

三条的缺陷都是**后处理性质**，不是生成质量：
  c1_0181  tail 静音 0.050s（要求 ≥0.06，regen_narr 的 TAIL 是 0.10）
  c3_0706  tail 静音 0.041s
  c2_0317  峰值 0.985（限 0.891）+ voiced RMS −27.3（目标 −24）

做法：
  1) 补尾静音到 0.10s（只在不足时补，不动有声段）
  2) 峰值超限 → 软限幅（tanh 膝盖）到 0.891，再整体缩放到目标电平
  3) 能量平均归一到 voiced RMS −24（与 716 条同口径：能量平均，不是 mean(db)）

不许做：改语速、拆句、句内包络二次处理、换 seed。
"""
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/_setup/_audio_ch123/out_bak_fix3"
TARGET_RMS = -24.0
PEAK_MAX = 0.891
TAIL_MIN = 0.10
SIL_DB = -45.0
IDS = ["c1_0181", "c3_0706", "c2_0317"]


def load(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


def voiced_mask(y, sr, win=0.02):
    f = max(1, int(win * sr))
    n = len(y) // f
    if n == 0:
        return np.zeros(len(y), bool)
    e = np.array([np.sqrt(np.mean(y[i * f:(i + 1) * f] ** 2)) for i in range(n)])
    db = 20 * np.log10(np.maximum(e, 1e-9))
    m = np.repeat(db > SIL_DB, f)
    return np.pad(m, (0, len(y) - len(m)), constant_values=False)


def voiced_rms_db(y, sr):
    """能量平均（与 716 条同口径）。"""
    m = voiced_mask(y, sr)
    if m.sum() == 0:
        return -99.0
    v = y[m]
    return float(20 * np.log10(max(np.sqrt(np.mean(v ** 2)), 1e-9)))


def tail_sil(y, sr):
    m = voiced_mask(y, sr)
    idx = np.where(m)[0]
    if len(idx) == 0:
        return len(y) / sr
    return (len(y) - 1 - idx[-1]) / sr


def soft_clip(y, ceiling):
    """膝盖在 0.7*ceiling 的 tanh 软限幅，只压尖峰，不动主体。"""
    knee = 0.7 * ceiling
    a = np.abs(y)
    out = y.copy()
    over = a > knee
    if over.any():
        sign = np.sign(y[over])
        x = (a[over] - knee) / (ceiling - knee)
        out[over] = sign * (knee + (ceiling - knee) * np.tanh(x))
    return out


def main():
    os.makedirs(BAK, exist_ok=True)
    dry = "--dry" in sys.argv
    rows = []
    for i in IDS:
        p = os.path.join(OUT, i + ".wav")
        if not os.path.exists(p):
            print("%-9s 文件缺" % i)
            continue
        y, sr = load(p)
        d0 = len(y) / sr
        r0 = voiced_rms_db(y, sr)
        t0 = tail_sil(y, sr)
        pk0 = float(np.abs(y).max())

        # 1) 峰值：超限先软限幅
        y1 = y
        clipped = False
        if pk0 > PEAK_MAX:
            y1 = soft_clip(y, PEAK_MAX)
            clipped = True

        # 2) 电平：能量平均归一到 −24
        r1 = voiced_rms_db(y1, sr)
        gain = 10 ** ((TARGET_RMS - r1) / 20.0)
        y2 = y1 * gain
        # 归一后再压一次峰值（增益可能把峰值推上去）
        pk2 = float(np.abs(y2).max())
        if pk2 > PEAK_MAX:
            y2 = y2 * (PEAK_MAX / pk2)

        # 3) 尾静音：不足则补到 0.10s
        t2 = tail_sil(y2, sr)
        pad = 0
        if t2 < TAIL_MIN:
            pad = int((TAIL_MIN - t2) * sr)
            y2 = np.concatenate([y2, np.zeros(pad, dtype=np.float32)])

        d1 = len(y2) / sr
        r2 = voiced_rms_db(y2, sr)
        pk3 = float(np.abs(y2).max())

        rows.append(dict(id=i, dur0=round(d0, 3), dur1=round(d1, 3),
                         rms0=round(r0, 2), rms1=round(r2, 2),
                         tail0=round(t0, 3), tail1=round(tail_sil(y2, sr), 3),
                         peak0=round(pk0, 3), peak1=round(pk3, 3),
                         clipped=clipped, pad_ms=round(pad / sr * 1000, 1)))
        print("%-9s dur %.2f→%.2f  rms %.1f→%.1f  tail %.3f→%.3f  peak %.3f→%.3f%s%s"
              % (i, d0, d1, r0, r2, t0, tail_sil(y2, sr), pk0, pk3,
                 "  [限幅]" if clipped else "", "  [补尾 %dms]" % (pad / sr * 1000) if pad else ""))
        if not dry:
            shutil.copy2(p, os.path.join(BAK, i + ".wav"))
            sf.write(p, y2.astype(np.float32), sr, subtype="PCM_16")

    json.dump(rows, open("G:/_setup/_fix3_log.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n%s  %s" % ("（--dry 未写盘）" if dry else "已回填，备份在 out_bak_fix3/",
                        "日志 _fix3_log.json"))


if __name__ == "__main__":
    main()
