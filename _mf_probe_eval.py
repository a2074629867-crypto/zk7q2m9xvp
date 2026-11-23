# -*- coding: utf-8 -*-
"""_mf_probe_eval.py —— 对同一句在不同推理步数下的输出做质量比对。

用法: python _mf_probe_eval.py <text> <wav1> <wav2> ...
输出: 时长 / voiced wpm / 频谱重心 / F0 中位 / ASR 文本 + 相似度 / 声纹(以第一个 wav 为锚) / NISQA
"""
import os
import sys
import difflib
import wave

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab")
import mt_spot as M
import spk_embed as SPK


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def stats(a, sr, nw):
    w = int(0.02 * sr)
    keep = [i for i in range(0, len(a) - w, w)
            if 20 * np.log10(np.sqrt((a[i:i + w] ** 2).mean()) + 1e-12) > -40]
    v = len(keep) * w / float(sr)
    dur = len(a) / float(sr)
    wpm = nw / v * 60.0 if v > 0.15 else 0.0
    cen = 0.0
    if keep:
        z = np.concatenate([a[i:i + w] for i in keep])
        sp = np.abs(np.fft.rfft(z * np.hanning(len(z))))
        fr = np.fft.rfftfreq(len(z), 1 / sr)
        cen = float((sp * fr).sum() / (sp.sum() + 1e-9))
    return dur, v, wpm, cen


def asr_text(path):
    try:
        import onnx_asr
    except Exception:
        return "<no-onnx_asr>"
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3")
    r = model.recognize(path)
    return r if isinstance(r, str) else getattr(r, "text", str(r))


def squash(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def main():
    text = sys.argv[1]
    paths = sys.argv[2:]
    nw = len(text.split())
    print("原文:", text, "(%d 词)" % nw)
    try:
        from speechmos import nisqa
        has_nisqa = True
    except Exception:
        has_nisqa = False
    anchor = None
    for p in paths:
        a, sr = rd(p)
        dur, v, wpm, cen = stats(a, sr, nw)
        try:
            f0 = M.f0med(a, sr)
        except Exception:
            f0 = float("nan")
        txt = asr_text(p)
        r = max(difflib.SequenceMatcher(None, text.lower().split(), txt.lower().split()).ratio(),
                difflib.SequenceMatcher(None, squash(text), squash(txt)).ratio())
        e = SPK.embed(p)
        if anchor is None:
            anchor = e
        c = SPK.cos(anchor, e)
        mos = float("nan")
        if has_nisqa:
            try:
                mos = float(nisqa.run(a[None, :].astype(np.float32), sr)["mos_pred"][0])
            except Exception:
                mos = float("nan")
        print("%-16s dur %5.2fs  wpm %5.0f  cen %5.0f  f0 %5.1f  sim %.3f  spk %.3f  mos %.2f"
              % (os.path.basename(p), dur, wpm, cen, f0, r, c, mos))
        print("    ASR:", txt)


if __name__ == "__main__":
    main()
