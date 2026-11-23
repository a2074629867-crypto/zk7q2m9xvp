# -*- coding: utf-8 -*-
"""导出 _step_test/*.wav 的词级时间戳到 _step_words.json（asr_venv 跑）。"""
import glob
import json
import os
import sys
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr

import os as _os
D = _os.environ.get("STEP_DIR", "G:/_setup/_step_test")
OUT = _os.environ.get("STEP_OUT", "G:/_setup/_step_words.json")


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
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


def to_words(tokens, ts, dur):
    out = []
    for tk, t in zip(tokens, ts):
        if tk.startswith(" ") or not out:
            out.append([tk.strip(), t])
        elif all(not c.isalnum() for c in tk):
            out.append([tk.strip(), t])
        else:
            out[-1][0] += tk
    for i in range(len(out) - 1):
        out[i].append(out[i + 1][1])
    out[-1].append(dur)
    return [dict(w=w, start=round(s, 3), end=round(e, 3)) for w, s, e in out]


def main():
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8", providers=[("CPUExecutionProvider", {})],
                            sess_options=so)
    tm = m.with_timestamps()
    files = sorted(glob.glob(os.path.join(D, "*.wav")))
    if len(sys.argv) > 1:
        files = [f for f in files if any(k in os.path.basename(f) for k in sys.argv[1:])]
    res = {}
    for p in files:
        try:
            a, sr = rd(p)
            dur = len(a) / sr
            r = tm.recognize(r16(a, sr))
            res[os.path.basename(p)] = {"text": r.text, "dur": round(dur, 3),
                                        "words": to_words(r.tokens, r.timestamps, dur)}
            print("%-14s %5.2fs %2d 词 | %s"
                  % (os.path.basename(p), dur, len(res[os.path.basename(p)]["words"]), r.text))
        except Exception as e:
            res[os.path.basename(p)] = {"error": str(e)[:120]}
            print(os.path.basename(p), "ERR", e)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", OUT, len(res))


if __name__ == "__main__":
    main()
