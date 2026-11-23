# -*- coding: utf-8 -*-
"""mt_asr_all.py —— 批量 ASR（在 asr_venv 下跑），产出 {路径: 转写} 的 JSON。

单独拆出来是因为 asr_venv 有 onnx_asr、default env 有 kaldi_native_fbank，
两个环境互不兼容，所以分两步：本脚本转写 → mt_score.py 打分择优。

用法：
    asr_venv/Scripts/python.exe mt_asr_all.py --dirs _mt_raw_s42,_mt_raw_s1234 --out _mt_asr.json
"""
import argparse
import glob
import json
import os
import sys
import wave

import numpy as np
import onnx_asr
import onnxruntime as ort

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def r16(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    files = []
    for d in a.dirs.split(","):
        files += sorted(glob.glob(os.path.join(os.path.abspath(d.strip()), "*.wav")))
    old = {}
    if os.path.exists(a.out):
        old = json.load(open(a.out, encoding="utf-8"))
    todo = [f for f in files if old.get(f) is None]
    print("共 %d 个文件，已有 %d，待转写 %d"
          % (len(files), len(files) - len(todo), len(todo)), flush=True)
    if not todo:
        return

    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL_DIR, quantization="int8",
                            providers=[("CPUExecutionProvider", {})], sess_options=so)
    res = dict(old)
    for i, p in enumerate(todo, 1):
        try:
            x, sr = rd(p)
            res[p] = (m.recognize(r16(x, sr)) or "").strip()
        except Exception as e:
            res[p] = ""
            print("  错误 %s: %s" % (os.path.basename(p), e), flush=True)
        if i % 50 == 0:
            print("  %d/%d" % (i, len(todo)), flush=True)
            json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("写完 %s（%d 条）" % (a.out, len(res)))


if __name__ == "__main__":
    main()
