# -*- coding: utf-8 -*-
"""切片标签交叉验证：Parakeet 回读切片音频 vs GSV 训练用 2-name2text.txt

目的：验证"文本-音频"是否对齐。若标签文本远长于/短于音频实际内容，
      GPT 微调就会学出"给一堆文本只吐几个 token 就 EOS"的塌缩行为。

用法： python verify_slice_labels.py [--n 40] [--seed 0]
"""
import argparse
import difflib
import json
import os
import random
import re
import sys
import time
import wave
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402
import onnx_asr  # noqa: E402

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
SLICED = Path("G:/GPT-SoVITS/_dataset_v5full/sliced_df3hp")
TEXTF = Path("G:/_setup/gsv5probe/logs/mcconaughey_v5full_df3hp/2-name2text.txt")


def read_wav_any(path):
    """读 wav，返回 (samples float32 mono, sr)"""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("unsupported sampwidth %d" % sw)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def resample_to_16k(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    x_old = np.arange(len(a), dtype=np.float64)
    x_new = np.linspace(0, len(a) - 1, n)
    return np.interp(x_new, x_old, a).astype(np.float32)


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(t.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit-zero", action="store_true", help="只看长度为0的极端片")
    args = ap.parse_args()

    # 读标签
    labels = {}
    for line in TEXTF.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        labels[Path(p[0]).name] = p[3]
    print("标签条数: %d" % len(labels), flush=True)

    files = sorted(SLICED.glob("*.wav"))
    print("切片文件数: %d" % len(files), flush=True)

    so = ort.SessionOptions()
    so.log_severity_level = 3
    model = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", MODEL_DIR,
        quantization="int8",
        providers=[("DmlExecutionProvider", {"device_id": 0})],
        sess_options=so,
    )
    print("模型已加载", flush=True)

    rnd = random.Random(args.seed)
    sample = rnd.sample(files, min(args.n, len(files)))
    sample = sorted(sample)

    rows = []
    t0 = time.time()
    for i, f in enumerate(sample):
        a, sr = read_wav_any(f)
        dur = len(a) / sr
        a16 = resample_to_16k(a, sr)
        try:
            hyp = model.recognize(a16, sample_rate=16000)
            if isinstance(hyp, list):
                hyp = hyp[0] if hyp else ""
        except Exception as e:  # noqa: BLE001
            hyp = "<ERR %s>" % e
        ref = labels.get(f.name, "<NO-LABEL>")

        r, h = norm(ref), norm(hyp)
        # 词级对齐
        sm = difflib.SequenceMatcher(None, r.split(), h.split())
        ratio = sm.ratio()
        # 音频实际时长 vs 标签朗读两秒估计：用 词数/秒
        wps_ref = len(ref.split()) / dur if dur else 0
        wps_hyp = len(hyp.split()) / dur if dur else 0
        rows.append(dict(file=f.name, dur=round(dur, 2), ref=ref, hyp=hyp,
                         ratio=round(ratio, 3),
                         nw_ref=len(ref.split()), nw_hyp=len(hyp.split()),
                         wps_ref=round(wps_ref, 2), wps_hyp=round(wps_hyp, 2)))
        print("[%2d/%d] %-46s %5.2fs  词 %2d/%2d  相似度 %.2f" %
              (i + 1, len(sample), f.name[-40:], dur, len(ref.split()),
               len(hyp.split()), ratio), flush=True)
        if ratio < 0.75:
            print("     标签: %s" % ref[:160])
            print("     实读: %s" % hyp[:160], flush=True)

    print("\n===== 汇总 (%.1fs) =====" % (time.time() - t0), flush=True)
    print("媒体相似度: %.3f  中位 %.3f" %
          (np.mean([x["ratio"] for x in rows]),
           float(np.median([x["ratio"] for x in rows]))))
    print("标签词/秒: 中位 %.2f  (正常英语朗读约 2.2-3.2)" %
          float(np.median([x["wps_ref"] for x in rows])))
    print("实读词/秒: 中位 %.2f" % float(np.median([x["wps_hyp"] for x in rows])))
    bad = [x for x in rows if x["ratio"] < 0.75]
    print("相似度<0.75 的片: %d/%d" % (len(bad), len(rows)))

    out = Path("G:/_setup/_slice_verify.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写 %s" % out, flush=True)


if __name__ == "__main__":
    main()
