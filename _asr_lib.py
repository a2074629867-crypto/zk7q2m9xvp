# -*- coding: utf-8 -*-
"""ASR 库：把 wav 转成词级时间戳。模型只加载一次，供回环反复调用。

    import _asr_lib
    res = _asr_lib.transcribe(["G:/_setup/_mt_raw_s42/N0001.wav"])
    # {path: {"dur":..., "text":..., "words":[{"w","start","end"}, ...]}}
"""
import os
import wave

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import onnxruntime as ort
import onnx_asr

_MODEL = None
_TOM = None
MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"
MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"


def _ensure():
    global _MODEL, _TOM
    if _TOM is not None:
        return
    so = ort.SessionOptions()
    so.log_severity_level = 3
    _MODEL = onnx_asr.load_model(MODEL_NAME, MODEL_DIR, quantization="int8",
                                providers=[("CPUExecutionProvider", {})],
                                sess_options=so)
    _TOM = _MODEL.with_timestamps()


def _read(p):
    with wave.open(p, "rb") as w:
        sr, ch, _sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def _r16(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def _to_words(tokens, ts, dur, lps=None):
    """子词 token → 词（拼接名字，结束时间 = 下一词起点）。

    lps 给了就带词置信度 p = exp(min(该词各子词 logprob))。
    取 min 不取 mean：吞字/读错通常只坑一个子词，平均会被同词其余子词稀释。
    """
    out = []
    for k, (tk, t) in enumerate(zip(tokens, ts)):
        lp = lps[k] if lps and k < len(lps) else None
        if tk.startswith(" ") or not out:
            out.append([tk.strip(), t, [lp]])
        elif all(not c.isalnum() for c in tk):
            out.append([tk.strip(), t, [lp]])
        else:
            out[-1][0] += tk
            out[-1][2].append(lp)
    for i in range(len(out) - 1):
        out[i].append(out[i + 1][1])
    if not out:
        return []
    out[-1].append(dur)
    rows = []
    for w, s, lst, e in out:
        d = dict(w=w, start=round(s, 3), end=round(e, 3))
        v = [x for x in lst if x is not None]
        if v:
            d["p"] = round(float(np.exp(min(v))), 3)
        rows.append(d)
    return rows


def _trim(a, sr, head_pad=0.05, tail_pad=0.25, fade=0.005):
    """裁掉首尾静音，返回 (音频, 起点偏移秒)。

    dots.tts 每段开头留 0.8~1.4s 静音（180 条 p50 1.22s）。不裁的话：
      1) ASR 容易在长静音上吐填充词 / 幻觉；
      2) 覆盖率检测把幻觉词算成「多念的」，判据被污染。
    口径与 mt_trim_head.py / _asr_qwen.py 一致（10ms 帧、90 分位 −25dB）。
    """
    fl, hop = 0.02, 0.01
    n = max(1, int(fl * sr))
    h = max(1, int(hop * sr))
    k = max(1, (len(a) - n) // h + 1)
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    np.clip(idx, 0, len(a) - 1, out=idx)
    r = np.sqrt((a[idx].astype(np.float64) ** 2).mean(1) + 1e-20)
    db = 20 * np.log10(r + 1e-12)
    if len(db) < 5:
        return a, 0.0
    on = db > (np.percentile(db, 90) - 25.0)
    if not on.any():
        return a, 0.0
    s0 = int(np.argmax(on)) * hop
    e0 = (len(on) - int(np.argmax(on[::-1]))) * hop
    s = max(0.0, s0 - head_pad)
    e = min(len(a) / sr, e0 + tail_pad)
    if e - s < 0.2:
        return a, 0.0
    y = a[int(s * sr):int(e * sr)].copy()
    nf = max(1, int(fade * sr))
    if len(y) > 2 * nf:
        ramp = np.linspace(0.0, 1.0, nf, dtype=np.float32)
        y[:nf] *= ramp
        y[-nf:] *= ramp[::-1]
    return y, s


def transcribe(paths, trim=False):
    _ensure()
    res = {}
    for p in paths:
        a, sr = _read(p)
        raw_dur = len(a) / sr
        off = 0.0
        if trim:
            a, off = _trim(a, sr)
        dur = len(a) / sr
        r = _TOM.recognize(_r16(a, sr))
        words = _to_words(r.tokens, r.timestamps, dur, getattr(r, "logprobs", None))
        # 时间戳是相对裁边后音频的，必须平移回原始 wav，否则 TextGrid 与音频错位
        if off > 0:
            for w in words:
                w["start"] = round(w["start"] + off, 3)
                w["end"] = round(w["end"] + off, 3)
        res[p] = dict(dur=round(raw_dur, 3), text=r.text, words=words)
    return res


if __name__ == "__main__":
    # CLI：必须用 asr_venv 的 python 跑（主环境没装 onnx_asr）
    #   asr_venv/Scripts/python.exe _asr_lib.py --out _words_loop.json a.wav b.wav
    #   asr_venv/Scripts/python.exe _asr_lib.py --out x.json --list paths.txt   # 路径太多时
    import argparse
    import json as _json
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_words_loop.json")
    ap.add_argument("--list", default=None, help="每行一个 wav 路径（命令行太长时用）")
    ap.add_argument("--append", action="store_true", help="合并进已有 --out 文件")
    ap.add_argument("--trim", action="store_true",
                    help="识别前裁掉首尾静音（时间戳已平移回原文件）")
    ap.add_argument("wavs", nargs="*")
    a = ap.parse_args()

    paths = list(a.wavs)
    if a.list:
        paths += [ln.strip().replace("\\", "/") for ln in open(a.list, encoding="utf-8")
                  if ln.strip()]
    if not paths:
        ap.error("没有输入 wav")
    old = {}
    if a.append and os.path.exists(a.out):
        old = _json.load(open(a.out, encoding="utf-8"))
    r = transcribe(paths, trim=a.trim)
    old.update(r)
    _json.dump(old, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("transcribed %d (total in file %d)" % (len(r), len(old)))
