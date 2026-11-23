# -*- coding: utf-8 -*-
"""逐条 ASR 校对：原文 vs 识别结果，词级 diff。

    asr_venv/Scripts/python.exe bk_asr_check.py [tag ...]
"""
import difflib
import os
import sys
import wave

import numpy as np
import onnx_asr
import onnxruntime as ort

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

OUT = "G:/_setup/dots_edit2"

# 与 castle_book_tts.py 完全一致
LINES = [
    ("1", "charles_normal", "It's called St Vincent's. That's nothing. It's only an old house. I'm all right."),
    ("2", "charles_soft", "I'm all right. I don't want to touch one, that's all. No. I'd rather not."),
    ("3", "charles_excited", "I'm a bowman, I'm the head warrior of this castle. If I shoot an arrow, I can kill you."),
    ("4", "charles_angry", "But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now."),
    ("5", "hooper_loud", "It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. You don't know what I might do to you, I could do anything at all."),
    ("6", "hooper_calm", "I'm King of the Castle! You'd better come down, show-off, if you fall you'll split your head open."),
    ("6b", "hooper_scold", "Open one of the cases, then. I'll let you. Why not? Scaredy-baby, scared of a moth! Pick one up."),
    ("7", "hooper_begging", "I don't like it here, I want to go home. I don't want to be lost. I want to go home."),
]


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


def norm(s):
    import re
    s = s.lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z' ]+", " ", s)
    return [w for w in s.split() if w]


def main():
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8",
                            providers=[("CPUExecutionProvider", {})], sess_options=so)
    want = set(sys.argv[1:])
    for tag, name, ref in LINES:
        if want and tag not in want:
            continue
        p = os.path.join(OUT, "BK_%s.wav" % tag)
        if not os.path.exists(p):
            print("[MISS] BK_%s" % tag)
            continue
        a, sr = rd(p)
        hyp = (m.recognize(r16(a, sr)) or "").strip()
        rw, hw = norm(ref), norm(hyp)
        sm = difflib.SequenceMatcher(None, rw, hw)
        bad = []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                continue
            bad.append("%s  ref[%s] -> asr[%s]" % (op, " ".join(rw[i1:i2]) or "-", " ".join(hw[j1:j2]) or "-"))
        acc = sm.ratio()
        print("=" * 78)
        print("BK_%-3s %-16s %5.2fs  词准 %.0f%%  (%d/%d)" % (tag, name, len(a) / sr, acc * 100, len(rw), len(hw)))
        print("  REF:", ref)
        print("  ASR:", hyp)
        for b in bad:
            print("   ! ", b)


if __name__ == "__main__":
    main()
