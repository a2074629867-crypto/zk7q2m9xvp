# -*- coding: utf-8 -*-
"""norm_dlg.py —— 对白 239 条电平归一（REQUIREMENTS 23）。

现状：voiced RMS 中位 −25.5，区间 −42.8 ~ −24.0，**跨度 18.8 dB**（要求 ≤1dB）。
旁白侧已经做到 0.32~0.40dB，对白一直没做。

做法：
  1) 只做整体增益，不动内容、不动语速、不动包络
  2) 目标 voiced RMS −24.0（能量平均，与旁白同口径，不是 mean(db)）
  3) 增益后若峰值 > 0.891 → 先软限幅再缩，保证不削波
  4) 每条的增益上限 ±12dB，超过的单独报出来（说明这条本身有问题，不该靠归一硬拉）

用法：
  G:/Python310/python.exe norm_dlg.py --dry
  G:/Python310/python.exe norm_dlg.py
"""
import argparse
import json
import os
import shutil

import numpy as np
import soundfile as sf

OUT = "G:/_setup/_audio_ch123/out"
BAK = "G:/_setup/_audio_ch123/out_bak_norm_1112"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
TARGET = -24.0
PEAK_MAX = 0.891
SIL_DB = -45.0
GAIN_LIMIT = 20.0   # c2_0365 峰值仅 0.053，需 17.9dB；+20dB 后峰值 0.42，不削波


def load(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


def voiced_mask(y, sr, win=0.02, rel_db=35.0):
    """相对阈值（峰值 −35dB）而不是绝对 −45dBFS。

    为什么：归一本身会改增益，绝对阈值下「哪些帧算有声」会随增益漂移 ——
    同一条音频在 −30 和 −24 两个电平上测出的 voiced RMS 差 1.5dB，
    于是「归一到 −24」永远收敛不了。相对阈值对增益不变，才是可用的尺子。
    """
    f = max(1, int(win * sr))
    n = len(y) // f
    if n == 0:
        return np.zeros(len(y), bool)
    e = np.array([np.sqrt(np.mean(y[i * f:(i + 1) * f] ** 2)) for i in range(n)])
    db = 20 * np.log10(np.maximum(e, 1e-9))
    thr = max(float(db.max()) - rel_db, -60.0)
    m = np.repeat(db > thr, f)
    return np.pad(m, (0, len(y) - len(m)), constant_values=False)


def vdb(y, sr):
    m = voiced_mask(y, sr)
    if m.sum() == 0:
        return -99.0
    v = y[m]
    return float(20 * np.log10(max(np.sqrt(np.mean(v ** 2)), 1e-9)))


def soft_clip(y, ceiling):
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    ids = []
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            ids.append(json.loads(l)["id"])

    os.makedirs(BAK, exist_ok=True)
    rows, skipped, over = [], [], []
    for i in ids:
        p = os.path.join(OUT, i + ".wav")
        if not os.path.exists(p):
            skipped.append(i)
            continue
        y, sr = load(p)
        r0 = vdb(y, sr)
        if r0 <= -90:
            skipped.append(i)
            continue
        gain = TARGET - r0
        if abs(gain) > GAIN_LIMIT:
            over.append((i, round(r0, 1), round(gain, 1)))
            continue
        y1 = y * (10 ** (gain / 20.0))
        clipped = False
        pk = float(np.abs(y1).max())
        if pk > PEAK_MAX:
            y1 = soft_clip(y1, PEAK_MAX)
            clipped = True
        r1 = vdb(y1, sr)
        rows.append((i, round(r0, 2), round(gain, 2), round(r1, 2),
                     round(float(np.abs(y1).max()), 3), clipped))
        if not a.dry:
            if not os.path.exists(os.path.join(BAK, i + ".wav")):
                shutil.copy2(p, os.path.join(BAK, i + ".wav"))
            sf.write(p, y1.astype(np.float32), sr, subtype="PCM_16")

    after = sorted(r[3] for r in rows)
    print("处理 %d 条 / 跳过 %d / 超增益上限 %d" % (len(rows), len(skipped), len(over)))
    if rows:
        print("归一后 voiced RMS：min %.2f  p05 %.2f  中位 %.2f  p95 %.2f  max %.2f  跨度 %.2f dB"
              % (after[0], after[int(len(after) * .05)], after[len(after) // 2],
                 after[int(len(after) * .95)], after[-1], after[-1] - after[0]))
        print("限幅 %d 条 · 峰值最大 %.3f" % (sum(1 for r in rows if r[5]),
                                          max(r[4] for r in rows)))
    if over:
        print("\n增益超 ±%.0fdB（本身有问题，未处理）：" % GAIN_LIMIT)
        for i, r0, g in over[:15]:
            print("  %-9s %.1f dBFS → 需 %.1f dB" % (i, r0, g))
    json.dump([dict(id=r[0], rms0=r[1], gain=r[2], rms1=r[3], peak=r[4], clip=r[5])
               for r in rows], open("G:/_setup/_norm_dlg_log.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n%s" % ("（--dry 未写盘）" if a.dry else "已回填，备份在 out_bak_norm_1112/"))


if __name__ == "__main__":
    main()
