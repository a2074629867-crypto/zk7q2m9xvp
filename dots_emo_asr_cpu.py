# -*- coding: utf-8 -*-
"""dots_emo_asr.py —— 回读 dots.tts 标签测试的产物，确认标签是否被当成文字念出"""
import os, re, glob, wave
import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
TARGET = "zoe drifted off to the soundest of sleeps"


def read_wav(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0 if sw == 2 else \
        np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def to16k(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return " ".join(t.split())


def main():
    so = ort.SessionOptions(); so.log_severity_level = 3
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL_DIR, quantization="int8",
                                providers=[("CPUExecutionProvider", {})], sess_options=so)
    print("模型已加载\n", flush=True)

    tn = norm(TARGET)
    for f in sorted(glob.glob(os.environ.get("PAT","G:/_setup/dots_emo/F*.wav"))):
        a, sr = read_wav(f)
        dur = len(a) / sr
        seg = to16k(a, sr)
        try:
            txt = model.recognize(seg) or ""
        except Exception as e:
            txt = "<ERR %s>" % str(e)[:60]
        nt = norm(txt)
        ratio = len(nt.split()) / max(len(tn.split()), 1)
        sim = difflib_ratio(nt, tn)
        print("%-14s %5.2fs  sim=%.3f  词比=%.2f  | %s" % (
            os.path.basename(f), dur, sim, ratio, txt[:90]), flush=True)


def difflib_ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


if __name__ == "__main__":
    main()
