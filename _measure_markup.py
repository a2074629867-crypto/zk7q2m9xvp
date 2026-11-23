# -*- coding: utf-8 -*-
"""四组标记格式对照实验的测量：时长 / ASR 词数 / 与原文相似度 / rate 兑现率"""
import os
import re
import json
import wave
import difflib

import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

BASE = "G:/_setup/dots_edit2"
VARIANTS = ["V_old_1", "V_new_1", "V_old_3", "V_new_3", "V_pause_old", "V_pause_new", "V_emo"]
REF_TEXT = open(os.path.join(BASE, "P1.txt"), encoding="utf-8").read().strip()
REF_WORDS = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", REF_TEXT))
SRC_S = 14.68   # P1 源音频时长


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
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


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(t.split())


so = ort.SessionOptions()
so.log_severity_level = 3
model = onnx_asr.load_model(
    "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
    quantization="int8", providers=[("CPUExecutionProvider", {})], sess_options=so)

rows = []
for v in VARIANTS:
    p = os.path.join(BASE, "MK_%s.wav" % v)
    if not os.path.exists(p):
        rows.append(dict(variant=v, missing=True))
        continue
    a, sr = rd(p)
    dur = len(a) / sr
    a16 = r16(a, sr)
    hyp = model.recognize(a16) or ""
    hyp = hyp or ""
    hw = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", hyp))
    sim = difflib.SequenceMatcher(None, norm(REF_TEXT), norm(hyp)).ratio()
    wpm = hw / dur * 60 if dur else 0
    rows.append(dict(variant=v, dur=round(dur, 2), hyp_words=hw,
                     ref_words=REF_WORDS, sim=round(sim, 4),
                     wpm=round(wpm, 1), hyp=hyp[:180]))

print("=" * 96)
print("源音频 %.2fs | 原文 %d 词" % (SRC_S, REF_WORDS))
print("-" * 96)
print("%-9s %7s %6s %6s %7s %7s  %s" % ("变体", "时长s", "ASR词", "原词", "相似度", "wpm", "判断"))
for r in rows:
    if r.get("missing"):
        print("%-9s   缺失" % r["variant"])
        continue
    flag = "正常" if r["hyp_words"] >= REF_WORDS * 0.92 else "★丢词"
    print("%-9s %7.2f %6d %6d %7.3f %7.1f  %s"
          % (r["variant"], r["dur"], r["hyp_words"], r["ref_words"],
             r["sim"], r["wpm"], flag))
print("-" * 96)
for r in rows:
    if not r.get("missing"):
        print("\n[%s] %s" % (r["variant"], r["hyp"]))

json.dump(dict(src_s=SRC_S, ref_words=REF_WORDS, rows=rows),
          open("G:/_setup/_markup_test_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n→ G:/_setup/_markup_test_result.json")
