# -*- coding: utf-8 -*-
"""第一步（asr_venv）：把所有变体的词级时间戳 + ASR 文本落成 JSON。

    asr_venv/Scripts/python.exe _perf_ts.py MP_ P_w_neg,P_w_pos,P_whole,P_mix

输出 _perf_ts.json:
  { "<variant>": {"dur":..,"text":"..","words":[[w,t0,t1],..]} , ... }
基线键名固定为 "BASE"。
"""
import json
import os
import re
import sys
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

D = "G:/_setup/dots_edit2/"
OUT = "G:/_setup/_perf_ts.json"


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def r16(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def merge(toks, ts):
    ws, cur, t0, t1 = [], "", None, None
    for tk, tt in zip(toks, ts):
        s = str(tk)
        if s.startswith(" "):
            if cur:
                ws.append([cur, t0, t1])
            cur, t0, t1 = s.strip(), tt, tt
        else:
            cur += s
            t1 = tt
    if cur:
        ws.append([cur, t0, t1])
    return ws


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = (sys.argv[2] if len(sys.argv) > 2 else "").split(",")
    variants = [v for v in variants if v]

    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
        quantization="int8", providers=[("CPUExecutionProvider", {})],
        sess_options=so).with_timestamps()

    res = {}
    jobs = [("BASE", D + "MKT_L_plain.wav")] + [(v, D + prefix + v + ".wav") for v in variants]
    for name, p in jobs:
        if not os.path.exists(p):
            print("MISSING", p)
            continue
        a, sr = rd(p)
        out = m.recognize(r16(a, sr))
        toks = getattr(out, "tokens", None) or []
        ts = getattr(out, "timestamps", None) or []
        ws = merge(toks, ts)
        txt = "".join(str(t) for t in toks)
        res[name] = dict(dur=round(len(a) / sr, 3),
                         text=txt,
                         words=[[w, round(float(a0), 3), round(float(b0), 3)]
                                for w, a0, b0 in ws])
        print("%-10s %.2fs  %d 词" % (name, len(a) / sr, len(ws)))

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", OUT)


if __name__ == "__main__":
    main()
