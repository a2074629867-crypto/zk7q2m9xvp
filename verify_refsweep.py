# -*- coding: utf-8 -*-
"""verify_refsweep.py —— 参考音频扫描产物的内容核对（Parakeet 回读 vs 目标文本）

用法：G:/_setup/asr_venv/Scripts/python.exe -u verify_refsweep.py
"""
import json, os, re, wave, difflib
import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
OUT = "E:/tts-models/acpp/out/refsweep"
TEXT = open("G:/_setup/scene_calmdeep.txt", encoding="utf-8").read().strip()


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
                                providers=[("DmlExecutionProvider", {"device_id": 0})], sess_options=so)
    print("模型已加载\n", flush=True)

    sweep = json.load(open(os.path.join(OUT, "sweep.json"), encoding="utf-8"))
    ref_w = norm(TEXT).split()
    print("目标文本 %d 词\n" % len(ref_w), flush=True)

    rows = []
    for r in sweep:
        if "path" not in r or not os.path.exists(r["path"]):
            continue
        a, sr = read_wav(r["path"])
        a16 = to16k(a, sr)
        try:
            h = model.recognize(a16, sample_rate=16000)
            if isinstance(h, list):
                h = h[0] if h else ""
        except Exception as e:  # noqa: BLE001
            h = "<ERR %s>" % e
        hn = norm(h).split()
        ratio = difflib.SequenceMatcher(None, ref_w, hn).ratio()
        missing = []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ref_w, hn).get_opcodes():
            if op in ("delete", "replace"):
                missing += ref_w[i1:i2]
        r.update(asr=round(ratio, 3), nw=len(hn), n_missing=len(missing),
                 missing=missing[:10], hyp=h[:200])
        rows.append(r)
        print("%-24s ref=%5.2fs out=%6.2fs  ASR=%.3f 词=%2d 缺=%d %s" % (
            r["tag"], r["ref_dur"], r["out_dur"], ratio, len(hn), len(missing),
            ("缺:" + " ".join(missing[:6])) if missing else ""), flush=True)

    json.dump(rows, open(os.path.join(OUT, "verify.json"), "w"), ensure_ascii=False, indent=1)
    print("\n已写 %s" % os.path.join(OUT, "verify.json"), flush=True)


if __name__ == "__main__":
    main()
