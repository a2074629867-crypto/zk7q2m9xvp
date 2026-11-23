# -*- coding: utf-8 -*-
"""Parakeet TDT 0.6B v3 —— 按 DF3 切片逐片转写，直接产出训练用 .list

为什么要按切片转：切片边界 = 真人真实停顿，逐片转写的结果天然与切片 1:1 对齐，
不需要 VAD 分块、不会有长程漂移，且输出格式直接就是 GSV 训练要的 .list。

用法：
  python parakeet_slices.py --sliced-dir <dir> --out <list> --json <json> [--limit N]
"""
import argparse
import json
import os
import re
import sys
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sliced-dir", required=True)
    ap.add_argument("--out", required=True, help="输出 .list（GSV 训练格式）")
    ap.add_argument("--json", required=True, help="输出 .json（含每片文本/时长）")
    ap.add_argument("--sr", type=int, default=32000, help="切片采样率（用于解析文件名帧号）")
    ap.add_argument("--batch", type=int, default=8, help="批大小")
    ap.add_argument("--provider", default="dml", choices=["dml", "cpu"])
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    so = ort.SessionOptions()
    so.log_severity_level = 3  # 只报 error，压掉 "Some nodes were not assigned" 噪音
    prov = ([("DmlExecutionProvider", {"device_id": 0})] if args.provider == "dml"
            else ["CPUExecutionProvider"])

    print("provider=%s  切片目录=%s" % (args.provider, args.sliced_dir), flush=True)
    import onnx_asr  # noqa: E402
    t0 = time.time()
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL_DIR,
                                quantization="int8", providers=prov, sess_options=so)
    print("模型加载 %.1fs" % (time.time() - t0), flush=True)

    # 收集切片并按时间排序
    files = [f for f in os.listdir(args.sliced_dir) if f.lower().endswith(".wav")]
    items = []
    for f in files:
        m = re.search(r"_(\d+)_(\d+)\.wav$", f)
        if not m:
            continue
        items.append(dict(file=f, t0=int(m.group(1)) / args.sr, t1=int(m.group(2)) / args.sr))
    items.sort(key=lambda s: s["t0"])
    if args.limit:
        items = items[: args.limit]
    print("切片 %d 段，总时长 %.1fs" % (len(items), sum(s["t1"] - s["t0"] for s in items)), flush=True)

    t_all = time.time()
    for i in range(0, len(items), args.batch):
        chunk = items[i: i + args.batch]
        paths = [os.path.join(args.sliced_dir, c["file"]) for c in chunk]
        try:
            outs = model.recognize(paths)
        except Exception as e:
            print("  批次 %d 失败(%s)，逐条重试" % (i, str(e)[:80]), flush=True)
            outs = []
            for p in paths:
                try:
                    outs.append(model.recognize(p))
                except Exception as e2:
                    print("    单条失败 %s: %s" % (os.path.basename(p), str(e2)[:60]), flush=True)
                    outs.append("")
        if isinstance(outs, str):
            outs = [outs]
        for c, o in zip(chunk, outs):
            c["text"] = (o or "").strip() if isinstance(o, str) else str(o).strip()
        if (i // args.batch) % 10 == 0:
            done = min(i + args.batch, len(items))
            el = time.time() - t_all
            print("  %4d/%d  已用 %.0fs" % (done, len(items), el), flush=True)

    total_dur = sum(s["t1"] - s["t0"] for s in items)
    el = time.time() - t_all
    nw = sum(len(s["text"].split()) for s in items)
    nempty = sum(1 for s in items if not s["text"])
    print("\n转写完成 %.0fs | RTFx=%.1f× | %d 词 | 空片 %d/%d"
          % (el, total_dur / max(el, 1e-6), nw, nempty, len(items)), flush=True)

    # 写 .list（相对路径，GSV 训练用）
    with open(args.out, "w", encoding="utf-8") as f:
        for s in items:
            if not s["text"]:
                continue
            f.write("%s|Calm|en|%s\n" % (s["file"], s["text"]))
    print("写出 %s（%d 行）" % (args.out, sum(1 for s in items if s["text"])), flush=True)

    json.dump(dict(provider=args.provider, sr=args.sr, n=len(items), n_words=nw,
                   total_dur=total_dur, elapsed=el, slices=items),
              open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % args.json, flush=True)

    print("\n前 6 片：", flush=True)
    for s in items[:6]:
        print("  [%7.2f-%7.2f] %s" % (s["t0"], s["t1"], s["text"][:110]), flush=True)
    print("空片列表:", [s["file"] for s in items if not s["text"]][:20], flush=True)


if __name__ == "__main__":
    main()
