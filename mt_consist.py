# -*- coding: utf-8 -*-
"""mt_consist.py —— 整章音色一致性（漂移检测）。

做法（按已固化的社区口径）：
- 12s 窗 / 6s 步长，丢掉有声不足 2s 的窗
- 每窗 CAM++ 声纹
- 簇中心用**均值**（逐维中位数在单位向量上会塌到 0.03，是坑）
- 输出：每窗与均值的余弦（σ / 最低 5 个窗）、每分钟块的余弦
  ⚠ σ 只有 0.08 量级，只用来排尾部，不设绝对阈值

用法：python mt_consist.py --wav _mt_out/ch1.wav
"""
import argparse
import os
import shutil
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
import spk_embed as SPK

WIN, HOP, MINV = 12.0, 6.0, 2.0


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def voiced(a, sr):
    w = int(0.02 * sr)
    v = []
    for i in range(0, len(a) - w, w):
        r = np.sqrt((a[i:i + w] ** 2).mean())
        if 20 * np.log10(r + 1e-12) > -45:
            v.append(w)
    return sum(v) / sr


def wr(p, a, sr):
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    a = ap.parse_args()
    x, sr = rd(a.wav)
    dur = len(x) / sr
    tmp = tempfile.mkdtemp(prefix="mtc_", dir="G:/_setup/_mt_tmp")
    paths, t0s = [], []
    t = 0.0
    while t + WIN <= dur:
        seg = x[int(t * sr):int((t + WIN) * sr)]
        if voiced(seg, sr) >= MINV:
            p = os.path.join(tmp, "w%06d.wav" % int(t * 10))
            wr(p, seg, sr)
            paths.append(p)
            t0s.append(t)
        t += HOP
    if len(paths) < 2:
        print("有效窗不足：%d" % len(paths))
        shutil.rmtree(tmp, ignore_errors=True)
        return
    E = np.stack([SPK.embed(p) for p in paths])
    c = E.mean(0)
    c /= np.linalg.norm(c)
    cos = E @ c
    order = np.argsort(cos)
    print("%s  %.1f 分钟 / %d 窗" % (os.path.basename(a.wav), dur / 60, len(paths)))
    print("  余弦 中位 %.3f  最低 %.3f  σ %.3f" % (np.median(cos), cos.min(), cos.std()))
    print("  最低 5 窗：" + "  ".join("%.0fs:%.2f" % (t0s[i], cos[i]) for i in order[:5]))
    # 每分钟块
    blk = {}
    for tt, cc in zip(t0s, cos):
        blk.setdefault(int(tt // 60), []).append(cc)
    bad = [(k, float(np.mean(v))) for k, v in sorted(blk.items()) if np.mean(v) < 0.75]
    bw = sorted([(k, float(np.mean(v))) for k, v in blk.items()], key=lambda x: x[1])
    print("  分钟块最低: " + "  ".join("%dm:%.2f" % (k, v) for k, v in bw[:5]))
    if bad:
        print("  ⚠ 低于 0.75 的分钟：" + ", ".join("%d:%.2f" % b for b in bad))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
