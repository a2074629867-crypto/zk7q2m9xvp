# -*- coding: utf-8 -*-
"""_asr_qwen.py —— 用 Qwen3-ASR-1.7B 做转写，输出与 _asr_words.py 相同的 json 结构。

为什么要换（2026-10-30）：
  Parakeet TDT v3 在缩写/连字符上口径不稳（mrs→misses、thirty-seven 合成），
  而且对童声 + 短句的鲁棒性没底。Qwen3-ASR-1.7B 是当前开源 SOTA，
  英文口音鲁棒性在官方评测里超过 Whisper-large-v3。

    pip install qwen-asr        （已装在 G:/Python312，独立于 G:/Python310）
    模型 G:/_setup/models/Qwen3-ASR-1.7B

输出 json 结构（与 _asr_words.py 一致，下游可直接吃）：
    { "<wav路径>": {"dur": 5.24, "text": "...", "words": [{"w": "...", "start": null, "end": null}] } }

注意：Qwen3-ASR 本身不吐词级时间戳（要配 Qwen3-ForcedAligner）。覆盖率检测只用
词序列，不需要时间戳，所以这里 start/end 留 null。若将来做重音对齐要用时间戳，
再挂 ForcedAligner，不要拿 null 当 0 用。

用法：
  G:/Python312/python.exe _asr_qwen.py --out _asr_trim_ch2_s42_qwen.json _mt_trim_ch2_s42/*.wav
  G:/Python312/python.exe _asr_qwen.py --list files.txt --out x.json
"""
import argparse
import json
import os
import re
import sys
import time
import wave

import numpy as np


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise SystemExit("只支持 16bit PCM：%s" % path)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def frame_db(x, sr, fl=0.02, hop=0.01):
    n = max(1, int(fl * sr))
    h = max(1, int(hop * sr))
    k = max(1, (len(x) - n) // h + 1)
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    np.clip(idx, 0, len(x) - 1, out=idx)
    r = np.sqrt((x[idx].astype(np.float64) ** 2).mean(1) + 1e-20)
    return 20 * np.log10(r + 1e-12)


def trim_silence(x, sr, head_pad=0.05, tail_pad=0.25, fade=0.005):
    """与 mt_trim_head.py 同口径的裁边（内联版，云端不必再带依赖）。

    dots.tts 每段开头留 0.8~1.4s 静音，不裁会让 ASR 吐填充词 / 误判。
    """
    db = frame_db(x, sr)
    if len(db) < 5:
        return x, 0.0, 0.0
    on = db > (np.percentile(db, 90) - 25.0)
    if not on.any():
        return x, 0.0, 0.0
    a = int(np.argmax(on)) * 0.01
    b = (len(on) - int(np.argmax(on[::-1]))) * 0.01
    s = max(0.0, a - head_pad)
    e = min(len(x) / sr, b + tail_pad)
    y = x[int(s * sr):int(e * sr)].copy()
    nf = max(1, int(fade * sr))
    if len(y) > 2 * nf:
        ramp = np.linspace(0.0, 1.0, nf, dtype=np.float32)
        y[:nf] *= ramp
        y[-nf:] *= ramp[::-1]
    return y, round(a - s, 3), round(e - b, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="*")
    ap.add_argument("--list", default=None, help="每行一个 wav 路径")
    ap.add_argument("--out", default="_asr_qwen.json")
    ap.add_argument("--model", default="G:/_setup/models/Qwen/Qwen3-ASR-1.7B",
                    help="modelscope 1.10 只认 cache_dir，实际落在 cache_dir/Qwen/Qwen3-ASR-1.7B")
    ap.add_argument("--lang", default="English", help="英文用 English；留空则自动识别")
    ap.add_argument("--dtype", default="auto", choices=["auto", "float32", "bfloat16", "float16"],
                    help="auto = 有 CUDA 用 bfloat16，否则 float32")
    ap.add_argument("--device", default="auto", help="auto / cuda / cpu")
    ap.add_argument("--trim", action="store_true",
                    help="内存内裁掉首尾静音再识别（与 mt_trim_head.py 同口径）")
    args = ap.parse_args()

    paths = list(args.wavs)
    if args.list:
        paths += [x.strip() for x in open(args.list, encoding="utf-8") if x.strip()]
    if not paths:
        raise SystemExit("没有输入 wav")

    import torch
    from qwen_asr import Qwen3ASRModel

    dev = args.device
    if dev == "auto":
        dev = "cuda" if torch.cuda.is_available() else "cpu"
    dt_name = args.dtype
    if dt_name == "auto":
        dt_name = "bfloat16" if dev == "cuda" else "float32"
    dt = {"float32": torch.float32, "bfloat16": torch.bfloat16, "float16": torch.float16}[dt_name]
    print("加载 %s (device=%s dtype=%s)" % (args.model, dev, dt_name))
    t0 = time.time()
    model = Qwen3ASRModel.from_pretrained(
        args.model,
        dtype=dt,
        device_map=dev,
        max_inference_batch_size=8,
        max_new_tokens=256,
    )
    print("模型加载 %.0fs" % (time.time() - t0))

    out = {}
    for i, p in enumerate(paths, 1):
        a, sr = read_wav(p)
        dur = len(a) / sr
        t = time.time()
        if args.trim:
            a, hp, tp = trim_silence(a, sr)
            print("    trim %s %.2fs -> %.2fs (head-%.2f tail-%.2f)"
                  % (os.path.basename(p), dur, len(a) / sr, hp, tp))
        try:
            kw = {"audio": [(a, sr)]}
            if args.lang:
                kw["language"] = [args.lang]
            r = model.transcribe(**kw)
            res = r[0] if isinstance(r, (list, tuple)) else r
            text = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else str(res))
        except Exception as e:
            text = ""
            print("  失败 %s: %s" % (os.path.basename(p), str(e)[:120]))
        words = [dict(w=w, start=None, end=None) for w in re.findall(r"[A-Za-z']+", text)]
        out[p] = dict(dur=round(dur, 3), text=text, words=words)
        print("[%d/%d] %-28s %5.2fs %2d词 %.1fs  %s"
              % (i, len(paths), os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p),
                 dur, len(words), time.time() - t, (text[:60] + "…") if len(text) > 60 else text))

    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s（%d 条）" % (args.out, len(out)))


if __name__ == "__main__":
    main()
