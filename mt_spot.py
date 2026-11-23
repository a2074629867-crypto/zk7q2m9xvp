# -*- coding: utf-8 -*-
"""mt_spot.py —— 抽检 mt 旁白批次（只读，不干扰正在跑的生成本体）。

量：时长 / 真 RMS / 峰值 / 尾部 5ms 落差 / F0 中位（抗八度） / 与 baseA 声纹。
用法：python mt_spot.py _mt_tmp/N0001_N0025/out
"""
import os, sys, glob, wave
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LAB = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
sys.path.insert(0, LAB)
import spk_embed as SPK

REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"


def rd(path):
    w = wave.open(path)
    ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    if sw == 2:
        y = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        y = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if ch > 1:
        y = y.reshape(-1, ch).mean(axis=1)
    return y, sr


def vrms(y, sr):
    w = int(0.02 * sr)
    v = []
    for i in range(0, len(y) - w, w):
        r = np.sqrt((y[i:i + w] ** 2).mean())
        if 20 * np.log10(r + 1e-12) > -45:
            v.append(r)
    return 20 * np.log10(np.sqrt(np.mean(np.square(v))) + 1e-12) if v else -120.0


def f0stats(y, sr):
    """返回 (中位, p10, p90)。自相关 F0，取「接近最大峰的最高频候选」以避免八度错误。"""
    hop, win = int(0.02 * sr), int(0.04 * sr)
    lo, hi = int(sr / 400), int(sr / 70)
    out = []
    for i in range(0, len(y) - win, hop):
        f = y[i:i + win]
        if np.sqrt((f ** 2).mean()) < 0.01:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if len(seg) < 3:
            continue
        norm = seg / ac[0]
        mx = float(norm.max())
        if mx < 0.3:
            continue
        # 第一个达到 0.85*max 的局部峰（周期最短 → F0 最高，抗八度下沉）
        k = None
        for j in range(1, len(norm) - 1):
            if norm[j] >= 0.85 * mx and norm[j] >= norm[j - 1] and norm[j] >= norm[j + 1]:
                k = j
                break
        if k is None:
            k = int(np.argmax(norm))
        out.append(sr / (k + lo))
    if not out:
        return 0.0, 0.0, 0.0
    a = np.array(out)
    return float(np.median(a)), float(np.percentile(a, 10)), float(np.percentile(a, 90))


def f0med(y, sr):
    return f0stats(y, sr)[0]


def tail_drop(y, sr):
    n = int(0.005 * sr)
    if len(y) < n * 2:
        return 0.0
    a = 20 * np.log10(np.sqrt((y[-2 * n:-n] ** 2).mean()) + 1e-12)
    b = 20 * np.log10(np.sqrt((y[-n:] ** 2).mean()) + 1e-12)
    return b - a


_EREF = None


def embed_ref():
    """baseA 参考声纹（只算一次）。"""
    global _EREF
    if _EREF is None:
        _EREF = SPK.embed(REF)
    return _EREF


def main():
    d = sys.argv[1]
    files = sorted(glob.glob(os.path.join(d, "*.wav")),
                   key=lambda p: int("".join(c for c in os.path.basename(p) if c.isdigit()) or 0))
    E_ref = SPK.embed(REF)
    print("baseA ref: %.2fs %dHz" % (len(rd(REF)[0]) / rd(REF)[1], rd(REF)[1]))
    print("%-12s %7s %7s %7s %8s %7s %7s" % ("file", "dur", "rms", "peak", "taildB", "F0", "spk"))
    bad = []
    for p in files:
        y, sr = rd(p)
        dur = len(y) / sr
        r, pk, td, f0 = vrms(y, sr), float(np.max(np.abs(y))), tail_drop(y, sr), f0med(y, sr)
        try:
            spk = SPK.cos(SPK.embed(p), E_ref)
        except Exception as e:
            spk = float("nan")
        flag = ""
        if td > -3:
            flag += " HARD-END"
        if spk == spk and spk < 0.65:
            flag += " SPK-LOW"
        if f0 > 305:
            flag += " F0-HIGH"
        print("%-12s %7.2f %7.1f %7.3f %8.1f %7.1f %7.3f%s"
              % (os.path.basename(p), dur, r, pk, td, f0, spk, flag))
        if flag:
            bad.append((os.path.basename(p), flag.strip(), round(spk, 3)))
    print("异常 %d 条" % len(bad))
    for b in bad:
        print("  ", b)


if __name__ == "__main__":
    main()
