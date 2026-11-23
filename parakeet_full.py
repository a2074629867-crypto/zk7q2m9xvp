# -*- coding: utf-8 -*-
"""Parakeet TDT 0.6B v3 —— 整段音频 + Silero VAD + 词级时间戳 → SRT / JSON

在**原始音频**上跑（不是 DF3）：实测 DF3 的数字零底噪会让 Parakeet 截断句尾，
原音的 -52dB 房间底噪则不会。我们只要文本，时间戳照旧映射到 DF3 切片。

用法：
  python parakeet_full.py --wav <16k mono wav> --out-srt <srt> --out-json <json>
"""
import argparse
import json
import os
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import onnxruntime as ort  # noqa: E402

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
VAD_DIR = "G:/_setup/models/silero-vad"


def ts(t, sep=","):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return "%02d:%02d:%02d%s%03d" % (h, m, int(s), sep, round((s - int(s)) * 1000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--out-srt", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--provider", default="dml", choices=["dml", "cpu"])
    args = ap.parse_args()

    so = ort.SessionOptions()
    so.log_severity_level = 3
    prov = ([("DmlExecutionProvider", {"device_id": 0})] if args.provider == "dml"
            else ["CPUExecutionProvider"])

    import onnx_asr  # noqa: E402

    t0 = time.time()
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL_DIR,
                                quantization="int8", providers=prov, sess_options=so)
    vad = onnx_asr.load_vad("silero", VAD_DIR, providers=["CPUExecutionProvider"], sess_options=so)
    print("模型+VAD 加载 %.1fs" % (time.time() - t0), flush=True)

    m = model.with_timestamps().with_vad(vad)
    print("开始整段转写: %s" % args.wav, flush=True)

    segs = []
    t0 = time.time()
    for i, res in enumerate(m.recognize(args.wav)):
        d = dict(start=float(res.start), end=float(res.end), text=str(res.text).strip())
        # 词级时间戳（若有）
        toks = getattr(res, "tokens", None)
        if toks:
            try:
                d["tokens"] = [[float(x[0]), float(x[1]), str(x[2])] for x in toks]
            except Exception:
                d["tokens"] = [list(map(str, x)) for x in toks]
        segs.append(d)
        if i < 8:
            print("  [%7.2f-%7.2f] %s" % (d["start"], d["end"], d["text"][:100]), flush=True)
        elif i % 25 == 0:
            print("  ... %d 段  已用 %.0fs" % (i, time.time() - t0), flush=True)
    el = time.time() - t0
    print("\n完成 %d 段 / %.0fs" % (len(segs), el), flush=True)

    total = sum(s["end"] - s["start"] for s in segs)
    nw = sum(len(s["text"].split()) for s in segs)
    print("语音总时长 %.1fs | %d 词 | 覆盖到 %.1fs" % (total, nw, segs[-1]["end"] if segs else 0), flush=True)

    with open(args.out_srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts(s["start"]), ts(s["end"]), s["text"]))
    print("写出 %s" % args.out_srt, flush=True)

    json.dump(dict(wav=args.wav, provider=args.provider, n=len(segs), n_words=nw,
                   speech_dur=total, elapsed=el, segments=segs),
              open(args.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % args.out_json, flush=True)


if __name__ == "__main__":
    main()
