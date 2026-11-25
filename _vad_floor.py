# -*- coding: utf-8 -*-
"""_vad_floor.py —— 用 VAD 而不是能量门限来统一底噪。

为什么必须换 VAD：
  能量门限（_denoise_floor.gate / _dn_uniform.unify_floor）判「非语音」靠
  「帧能量 < 峰值−N dB」。高底噪条（−36 dBFS）的静音段能量本来就高，
  永远落在阈值之上 ⇒ 被判成语音、一点不降。实测 c1_0154 底噪 −34.7，
  门限和 demucs 都只能到 −40 左右。
  silero-vad 是神经网络判「这里有没有人在说话」，与能量无关，高底噪下仍然准。

链路：48k → 降 16k 跑 VAD（512 点/帧 = 32ms）→ 概率包络插值回 48k
      → 非语音段压到 floor_db 并叠恒定底噪 → 语音段原样（可选先用 DeepFilterNet 去噪）

用法：
  G:/Python310/python.exe _vad_floor.py --in _audio_ch123/out --out _vad --ids c1_0154,c2_0447
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import onnxruntime as ort
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VAD = "G:/_setup/models/silero-vad/silero_vad.onnx"
SR_OUT = 48000
SR_VAD = 16000
FRAME = 512


def resample(y, sr_in, sr_out):
    if sr_in == sr_out:
        return y
    n = int(round(len(y) * sr_out / sr_in))
    t_in = np.arange(len(y)) / sr_in
    return np.interp(np.linspace(0, t_in[-1], n), t_in, y).astype(np.float32)


class Vad:
    def __init__(self, path=VAD):
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.s = ort.InferenceSession(path, sess_options=so,
                                      providers=[("CPUExecutionProvider", {})])

    def probs(self, y16):
        """返回每 512 点的语音概率。"""
        state = np.zeros((2, 1, 128), dtype=np.float32)
        sr = np.array(SR_VAD, dtype=np.int64)
        n = len(y16) // FRAME
        out = np.zeros(n, dtype=np.float32)
        for i in range(n):
            chunk = y16[i * FRAME:(i + 1) * FRAME].astype(np.float32)[None, :]
            p, state = self.s.run(None, {"input": chunk, "state": state, "sr": sr})
            out[i] = float(p.squeeze())
        return out


def frame_db(y, sr, win=0.01, hop=0.01):
    """与 dialog_gate.audio_stats 同口径（10ms 方窗 / 10ms 跳），保证数字可对比。"""
    w, h = int(win * sr), int(hop * sr)
    n = max(1, len(y) // h)
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(n)[:, None], 0, len(y) - 1)
    e = np.sqrt((y[idx] ** 2).mean(1)) + 1e-12
    return 20 * np.log10(e)


def apply_floor(y, sr, prob, thr=0.35, floor_db=-72.0, ramp_ms=30.0, seed=0):
    """prob 是 32ms 分辨率；插值到采样点后作为「非语音权重」。"""
    centers = (np.arange(len(prob)) + 0.5) * FRAME / SR_VAD
    p_samp = np.interp(np.arange(len(y)) / sr, centers, prob, left=prob[0], right=prob[-1])
    gate = np.clip((thr - p_samp) / max(thr, 1e-6), 0.0, 1.0)  # prob 越低越接近 1
    # 平滑
    k = max(1, int(ramp_ms / 1000 * sr))
    ker = np.hanning(2 * k + 1); ker /= ker.sum()
    gate = np.convolve(np.pad(gate, k, mode="edge"), ker, mode="valid")[: len(y)]
    rng = np.random.default_rng(seed)
    nz = rng.standard_normal(len(y))
    nz = nz / (np.sqrt((nz ** 2).mean()) + 1e-12) * (10 ** (floor_db / 20.0))
    return (y * (1 - gate) + y * 0.02 * gate + nz * gate).astype(np.float32), gate


def norm_rms(y, sr, target=-24.0):
    db = frame_db(y, sr)
    m = db > np.percentile(db, 70)
    w = int(0.01 * sr)
    n = max(1, len(y) // w)
    idx = np.clip(np.arange(w)[None, :] + w * np.arange(n)[:, None], 0, len(y) - 1)
    seg = y[idx][:len(m)][m] if False else y.reshape(-1, 1)
    # 直接按 voiced 帧取样本
    fr = y[:n * w].reshape(n, w)
    voiced = fr[m[:n]] if len(m) >= n else fr
    r = np.sqrt((voiced ** 2).mean()) + 1e-12
    return (y * (10 ** ((target - 20 * np.log10(r)) / 20.0))).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--out", default="G:/_setup/_vad")
    ap.add_argument("--ids", default="")
    ap.add_argument("--thr", type=float, default=0.35)
    ap.add_argument("--floor", type=float, default=-72.0)
    ap.add_argument("--norm", type=float, default=-24.0)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", default="G:/_setup/_vad_report.json")
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = ([os.path.join(a.inp, i + ".wav") for i in ids] if ids
             else sorted(glob.glob(os.path.join(a.inp, "*.wav"))))
    if not a.probe:
        os.makedirs(a.out, exist_ok=True)
    vad = Vad()
    rep = {}
    for f in files:
        if not os.path.exists(f):
            print("缺", f)
            continue
        y, sr = sf.read(f, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        y48 = resample(y, sr, SR_OUT)
        y16 = resample(y48, SR_OUT, SR_VAD)
        p = vad.probs(y16)
        z, gate = apply_floor(y48, SR_OUT, p, a.thr, a.floor)
        if a.norm:
            z = norm_rms(z, SR_OUT, a.norm)
            pk = float(np.abs(z).max())
            if pk > 0.97:
                z = (z * (0.97 / pk)).astype(np.float32)
        db0, db1 = frame_db(y48, SR_OUT), frame_db(z, SR_OUT)
        f0 = float(np.percentile(db0, 10)); f1 = float(np.percentile(db1, 10))
        s0 = float(np.percentile(db0, 95) - f0); s1 = float(np.percentile(db1, 95) - f1)
        tag = os.path.basename(f)[:-4]
        rep[tag] = dict(floor_before=round(f0, 1), floor_after=round(f1, 1),
                        snr_before=round(s0, 1), snr_after=round(s1, 1),
                        speech_frac=round(float((p > a.thr).mean()), 3),
                        peak=round(float(np.abs(z).max()), 3), dur=round(len(z) / SR_OUT, 2))
        print("%-10s 语音占 %4.0f%%  底噪 %6.1f→%6.1f  SNR %4.1f→%4.1f" %
              (tag, 100 * rep[tag]["speech_frac"], f0, f1, s0, s1))
        if not a.probe:
            sf.write(os.path.join(a.out, tag + ".wav"), z, SR_OUT, subtype="PCM_24")
    if a.report and not a.probe:
        json.dump(rep, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("-> %s" % a.report)


if __name__ == "__main__":
    main()
