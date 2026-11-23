# -*- coding: utf-8 -*-
"""验证多 rate span 是否分段生效：按词级时间戳算每段的 wpm"""
import os
import re
import json
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

BASE = "G:/_setup/dots_edit2"
# 三段文本与各自被赋予的 rate
SEGS = [
    ("S1", "A stock of prized possessions sat on Zoe's shelves.", 0.90),
    ("S2", "Dinosaur figurines picture books, and a paper mache giraffe.", 0.70),
    ("S3", "Purple thumbtacks held some of her finest drawings on the wall.", 0.80),
]


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
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


def merge_tokens(tokens, times):
    words, cur, cs, ce = [], "", None, None
    for tok, t in zip(tokens, times):
        if tok.startswith(" ") or cur == "":
            if cur:
                words.append((cur, cs, ce))
            cur, cs, ce = tok.strip(), t, t
        else:
            cur += tok
            ce = t
    if cur:
        words.append((cur, cs, ce))
    return words


so = ort.SessionOptions()
so.log_severity_level = 3
model = onnx_asr.load_model(
    "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
    quantization="int8", providers=[("CPUExecutionProvider", {})],
    sess_options=so).with_timestamps()

# 三段的首词 / 末词，用于按词序号切段
FIRST = ["stock", "dinosaur", "purple"]
# 每段词数（按原文）
NW = [9, 10, 11]

for v in ["V_old_1", "V_new_1", "V_old_3", "V_new_3"]:
    p = os.path.join(BASE, "MK_%s.wav" % v)
    a, sr = rd(p)
    a16 = r16(a, sr)
    out = model.recognize(a16, sample_rate=16000)
    text = getattr(out, "text", "")
    toks = getattr(out, "tokens", None) or []
    times = getattr(out, "timestamps", None) or []
    words = merge_tokens(toks, times) if toks else []
    print("\n" + "=" * 78)
    print("[%s] 总时长 %.2fs | 识别 %d 词" % (v, len(a) / sr, len(words)))
    if not words:
        print("  (无词级时间戳，跳过分段)")
        print("  text:", str(text)[:150])
        continue
    # 按首词定位三段起点
    starts = []
    for f in FIRST:
        idx = next((i for i, w in enumerate(words) if w[0].lower().strip("',.") == f), None)
        starts.append(idx)
    print("  三段首词索引:", starts)
    bounds = [s for s in starts if s is not None] + [len(words)]
    for k in range(len(starts)):
        if starts[k] is None:
            continue
        a_i = starts[k]
        b_i = starts[k + 1] if k + 1 < len(starts) and starts[k + 1] else len(words)
        seg = words[a_i:b_i]
        if len(seg) < 2:
            continue
        t0, t1 = seg[0][1], seg[-1][2]
        dur = t1 - t0
        nw = len(seg)
        wpm = nw / dur * 60 if dur > 0 else 0
        print("  %s rate=%.2f | %2d 词 %5.2fs | %6.1f wpm | %s"
              % (SEGS[k][0], SEGS[k][2], nw, dur, wpm,
                 " ".join(w[0] for w in seg)[:60]))
