# -*- coding: utf-8 -*-
"""用 Silero VAD 做「有声但是不是人声」的覆盖率检测。

思路来源（开源社区标准做法）：
  URGENT Challenge 的 filter_via_vad.py —— 用 VAD 剔除「有能量但其实不是语音」的样本。
  DNS Challenge 的 DNSMOS BAK 也是同一个逻辑：模型只「在有人声的地方」听背景。

我们之前用的是能量阈值（split_at_silence）判「有没有声音」，
但能量高 ≠ 是人声：rubberband 过度拉伸、气流噪声、模型进假声区，
都会产生「能量很足但 VAD 不认」的片段。这类片段人耳听到的就是「炸」「毛」「不像人」。

指标：
  cov = VAD 判为语音的时长 / 有声段总时长
  cov < 0.85  → 该条有「有声非人声」的段
  cov < 0.70  → 严重，基本是伪影

用法：
  python ch123_vadcov.py ch123_clean          # 全库
  python ch123_vadcov.py ch123_clean/L078.wav # 单条（打印逐段）
"""
import os
import sys
import wave

import numpy as np
import onnxruntime as ort
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB

VAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models/silero-vad/silero_vad.onnx")
SR_VAD = 16000
WIN = 512          # Silero 固定窗长 @16k = 32ms
THR = 0.5


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("unsupported sampwidth %d" % sw)
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def vad_probs(a, sr):
    """返回 (probs, 每帧对应的原始时间轴起点数组)"""
    if sr != SR_VAD:
        g = np.gcd(SR_VAD, sr)
        a = resample_poly(a, SR_VAD // g, sr // g).astype(np.float32)
    sess = ort.InferenceSession(VAD, providers=["CPUExecutionProvider"])
    state = np.zeros((2, 1, 128), dtype=np.float32)
    n = len(a) // WIN
    probs = np.zeros(n, dtype=np.float32)
    for i in range(n):
        chunk = a[i * WIN:(i + 1) * WIN].reshape(1, -1)
        out, state = sess.run(None, {"input": chunk, "state": state,
                                     "sr": np.array(SR_VAD, dtype=np.int64)})
        probs[i] = float(out[0][0])
    return probs, a


def analyze(path, verbose=False):
    a, sr = read_wav(path)
    probs, _ = vad_probs(a, sr)
    # 每帧 = 512/16000 = 32ms
    hop = WIN / SR_VAD
    segs = [(s0, s1) for s0, s1 in RB.split_at_silence(a, sr, min_gap=0.12) if s1 - s0 >= 0.20]

    total = 0.0
    voiced = 0.0
    rows = []
    for s0, s1 in segs:
        i0 = int(s0 / hop)
        i1 = max(i0 + 1, int(s1 / hop))
        p = probs[i0:i1]
        if len(p) == 0:
            continue
        d = s1 - s0
        v = float((p >= THR).mean()) * d
        total += d
        voiced += v
        rows.append((s0, s1, d, v / d, float(p.mean())))
    cov = voiced / total if total > 0 else 0.0

    if verbose:
        print("%s  %.2fs  %d 段  覆盖率 %.1f%%" % (os.path.basename(path), len(a) / sr, len(rows), cov * 100))
        print("  %-4s %11s %6s %8s %8s" % ("段", "起-止", "时长", "VAD覆盖", "平均概率"))
        for i, (s0, s1, d, c, m) in enumerate(rows):
            tag = "OK" if c >= 0.85 else ("⚠ 有声非人声" if c >= 0.70 else "✗ 基本是伪影")
            print("  p%-3d %5.2f-%5.2f %6.2fs %7.0f%% %8.2f  %s" % (i, s0, s1, d, c * 100, m, tag))
    return cov, rows, len(a) / sr


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    tgt = args[0]
    if os.path.isdir(tgt):
        files = sorted(f for f in os.listdir(tgt) if f.endswith(".wav"))
        out = []
        for f in files:
            p = os.path.join(tgt, f)
            try:
                cov, rows, dur = analyze(p)
            except Exception as e:
                print("%-8s ERR %s" % (f[:-4], e))
                continue
            worst = min((r[3] for r in rows), default=1.0)
            out.append((f[:-4], cov, worst, dur))
        print("%-8s %8s %8s %6s" % ("id", "覆盖率", "最差段", "时长"))
        for k, c, w, d in sorted(out, key=lambda x: x[1]):
            flag = "" if c >= 0.85 else ("  ⚠" if c >= 0.70 else "  ✗")
            print("%-8s %7.1f%% %7.0f%% %5.2fs%s" % (k, c * 100, w * 100, d, flag))
        cv = np.array([x[1] for x in out])
        print("\nn=%d  中位 %.1f%%  最低 %.1f%%  <85%% 的 %d 条"
              % (len(out), np.median(cv) * 100, cv.min() * 100, int((cv < 0.85).sum())))
    else:
        analyze(tgt, verbose=True)


if __name__ == "__main__":
    main()
