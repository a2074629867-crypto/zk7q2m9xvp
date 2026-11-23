# -*- coding: utf-8 -*-
"""verify_v6_out.py —— 用 Parakeet 回读 v6 各 epoch 生成的音频，核对内容是否完整正确

判定：时长接近 base（~20.8s）且 ASR 文本相似度高 => 该 epoch 可用。
"""
import glob
import os
import re
import sys
import wave
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np
import onnxruntime as ort
import onnx_asr
import difflib

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
OUTDIR = Path("E:/tts-models/acpp/out/v6full")
TEXT = open("G:/_setup/scene_calmdeep.txt", encoding="utf-8").read().strip()


def read_wav_any(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate(); ch = w.getnchannels(); sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("sampwidth %d" % sw)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def resample_to_16k(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9']+", " ", t)
    return " ".join(t.split())


def main():
    so = ort.SessionOptions(); so.log_severity_level = 3
    model = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", MODEL_DIR, quantization="int8",
        providers=[("DmlExecutionProvider", {"device_id": 0})], sess_options=so)
    print("模型已加载\n", flush=True)

    ref_n = norm(TEXT)
    ref_w = ref_n.split()
    print("源文本: %d 词\n" % len(ref_w), flush=True)

    files = [OUTDIR / "v6_base.wav"]
    eps = sorted(glob.glob(str(OUTDIR / "v6_e*.wav")),
                 key=lambda p: int(re.search(r"e(\d+)", p).group(1)))
    files += [Path(p) for p in eps]

    rows = []
    for f in files:
        if not f.exists():
            print("[MISS] %s" % f.name, flush=True); continue
        tag = f.stem.replace("v6_", "")
        a, sr = read_wav_any(f)
        dur = len(a) / sr
        a16 = resample_to_16k(a, sr)
        try:
            h = model.recognize(a16, sample_rate=16000)
            if isinstance(h, list):
                h = h[0] if h else ""
        except Exception as e:  # noqa: BLE001
            h = "<ERR %s>" % e
        hn = norm(h); hw = hn.split()
        sm = difflib.SequenceMatcher(None, ref_w, hw)
        ratio = sm.ratio()
        # 缺失词（源里有、输出没提）
        missing = []
        sm2 = difflib.SequenceMatcher(None, ref_w, hw)
        for op, i1, i2, j1, j2 in sm2.get_opcodes():
            if op in ("delete", "replace"):
                missing += ref_w[i1:i2]
        rows.append(dict(tag=tag, dur=round(dur, 2), nw=len(hw),
                         ratio=round(ratio, 3), missing=missing[:12],
                         n_missing=len(missing)))
        print("%-6s %6.2fs  识别 %3d 词  相似度 %.3f  缺 %d 词  %s" % (
            tag, dur, len(hw), ratio, len(missing),
            ("缺:" + " ".join(missing[:8])) if missing else ""), flush=True)

    print("\n===== 汇总 =====", flush=True)
    ok = [r for r in rows if r["dur"] > 15 and r["ratio"] > 0.80]
    print("候选可用(dur>15s 且 相似度>0.80): %s" % [r["tag"] for r in ok], flush=True)
    import json
    json.dump(rows, open(str(OUTDIR / "asr_check.json"), "w"),
              ensure_ascii=False, indent=1)
    print("已写 %s" % (OUTDIR / "asr_check.json"), flush=True)


if __name__ == "__main__":
    main()
