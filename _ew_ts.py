# -*- coding: utf-8 -*-
"""单词级 emo 实验第一步（asr_venv）：多变体 ASR + 词级时间戳 → _ew_ts.json

    asr_venv/Scripts/python.exe _ew_ts.py EW_emo_auto,EW_emo_xv,...

基线固定用 MES_ES_base.wav（同链路、同 seed、无标签）。
"""
import json
import os
import sys
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

D = "G:/_setup/dots_edit2/"
OUT = "G:/_setup/_ew_ts.json"
BASE = "ES_base"


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
                ws.append([cur, float(t0), float(t1)])
            cur, t0, t1 = s.strip(), tt, tt
        else:
            cur += s
            t1 = tt
    if cur:
        ws.append([cur, float(t0), float(t1)])
    return ws


def main():
    variants = [v for v in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if v]
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
        quantization="int8", providers=[("CPUExecutionProvider", {})],
        sess_options=so).with_timestamps()

    res = {}
    for name, p in [(BASE, D + "MES_ES_base.wav")] + \
                   [(v, D + "MES_" + v + ".wav") for v in variants]:
        if not os.path.exists(p):
            print("MISSING", p)
            continue
        a, sr = rd(p)
        out = m.recognize(r16(a, sr))
        toks = getattr(out, "tokens", None) or []
        ts = getattr(out, "timestamps", None) or []
        ws = merge(toks, ts)
        res[name] = dict(dur=round(len(a) / sr, 3),
                         text="".join(str(t) for t in toks),
                         words=ws)
        print("%-16s %.2fs  %d 词" % (name, len(a) / sr, len(ws)))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", OUT)


if __name__ == "__main__":
    main()
