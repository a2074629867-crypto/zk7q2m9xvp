# -*- coding: utf-8 -*-
"""长文本（130 词）标记实验测量：时长 / ASR 词数 / 相似度 / wpm / 静音占比 / 间隙序列"""
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
VARIANTS = ["L_plain", "L_1", "L_9", "L_pause", "L_emo"]
REF_TEXT = open(os.path.join(BASE, "L_plain.txt"), encoding="utf-8").read().strip()
REF_WORDS = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", REF_TEXT))


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


def vads(a, sr, thr_db=-35.0, hop_ms=10):
    """能量 VAD：返回 (语音段列表, 间隙列表)"""
    hop = int(sr * hop_ms / 1000)
    n = len(a) // hop
    if n == 0:
        return [], []
    db = 20 * np.log10(np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() + thr_db)
    # 填 <80ms 洞
    fill = 8
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < fill:
                m[i:j] = True
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            segs.append((i * hop / sr, j * hop / sr))
            i = j
        else:
            i += 1
    gaps = []
    for k in range(1, len(segs)):
        g0, g1 = segs[k - 1][1], segs[k][0]
        if g1 - g0 >= 0.06:
            gaps.append(round(g1 - g0, 3))
    return segs, gaps


so = ort.SessionOptions()
so.log_severity_level = 3
model = onnx_asr.load_model(
    "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
    quantization="int8", providers=[("CPUExecutionProvider", {})], sess_options=so)

rows = []
for v in VARIANTS:
    p = os.path.join(BASE, "MKL_%s.wav" % v)
    if not os.path.exists(p):
        rows.append(dict(variant=v, missing=True))
        continue
    a, sr = rd(p)
    dur = len(a) / sr
    segs, gaps = vads(a, sr)
    sp = sum(b - c for c, b in segs)
    hyp = model.recognize(r16(a, sr)) or ""
    hw = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", hyp))
    sim = difflib.SequenceMatcher(None, norm(REF_TEXT), norm(hyp)).ratio()
    rows.append(dict(
        variant=v, dur=round(dur, 2), hyp_words=hw, ref_words=REF_WORDS,
        sim=round(sim, 4),
        wpm_all=round(hw / dur * 60, 1) if dur else 0,
        wpm_speech=round(hw / sp * 60, 1) if sp else 0,
        speech_s=round(sp, 2), silence_pct=round(100 * (dur - sp) / dur, 1),
        n_gaps=len(gaps),
        gap_med=round(float(np.median(gaps)), 3) if gaps else None,
        gaps=gaps[:30],
        hyp=hyp[:260]))

print("=" * 104)
print("原文 %d 词 / %d 句" % (REF_WORDS, len(re.findall(r"[.!?]", REF_TEXT))))
print("-" * 104)
print("%-8s %7s %6s %7s %7s %8s %7s %6s %7s  %s"
      % ("变体", "时长s", "ASR词", "相似", "语音wpm", "语音s", "静音%", "间隙n", "中位", "判断"))
for r in rows:
    if r.get("missing"):
        print("%-8s  缺失" % r["variant"])
        continue
    flag = "正常" if r["hyp_words"] >= REF_WORDS * 0.92 else "★丢词"
    print("%-8s %7.2f %6d %7.3f %7.1f %8.2f %7.1f %6d %7s  %s"
          % (r["variant"], r["dur"], r["hyp_words"], r["sim"], r["wpm_speech"],
             r["speech_s"], r["silence_pct"], r["n_gaps"],
             r["gap_med"] if r["gap_med"] else "-", flag))
print("-" * 104)
for r in rows:
    if not r.get("missing"):
        print("\n[%s] 间隙 %s" % (r["variant"], r["gaps"]))
        print("     %s" % r["hyp"])

json.dump(dict(ref_words=REF_WORDS, rows=rows),
          open("G:/_setup/_long_test_result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n→ G:/_setup/_long_test_result.json")
