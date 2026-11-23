# -*- coding: utf-8 -*-
"""Parakeet TDT 0.6B v3 —— DirectML(GPU) vs CPU 对比测试

验证 RX 580 能否通过 DirectML 跑 Parakeet，并对比 CPU 的 RTFx。
测试音频 = disputed 段（170-200s）：small.en 说是 "leaves gliding down..."，
large-v3-turbo 崩成 "I'm going to go from the point of view of the world..."。
"""
import os
import sys
import time
import wave

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

print("=" * 72, flush=True)
print("onnxruntime %s" % ort.__version__, flush=True)
print("available providers: %s" % ort.get_available_providers(), flush=True)
print("=" * 72, flush=True)

import onnx_asr  # noqa: E402

print("onnx_asr %s" % getattr(onnx_asr, "__version__", "?"), flush=True)

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"
WAV = "G:/_setup/_verify/wav/disputed_170-200.wav"
if not os.path.exists(WAV):
    WAV = "G:/_setup/_verify/disputed_170-200.wav"
assert os.path.exists(WAV), "找不到测试音频: " + WAV

with wave.open(WAV, "rb") as w:
    dur = w.getnframes() / w.getframerate()
    sr = w.getframerate()
print("测试音频: %s" % WAV, flush=True)
print("时长 %.2fs @ %d Hz" % (dur, sr), flush=True)
print("=" * 72, flush=True)

# 打印 load_model 签名，确认参数名
import inspect  # noqa: E402
try:
    print("load_model 签名: %s" % inspect.signature(onnx_asr.load_model), flush=True)
except Exception as e:
    print("签名获取失败: %s" % e, flush=True)
print("=" * 72, flush=True)


def run(tag, providers):
    print("\n---- [%s] providers=%s ----" % (tag, providers), flush=True)
    try:
        t0 = time.time()
        m = onnx_asr.load_model(
            "nemo-parakeet-tdt-0.6b-v3",
            MODEL_DIR,
            quantization="int8",
            providers=providers,
        )
        t_load = time.time() - t0
        print("  加载 %.1fs" % t_load, flush=True)
    except Exception as e:
        print("  !! 加载失败: %s: %s" % (type(e).__name__, str(e)[:500]), flush=True)
        return None

    for attr in ("_session", "session", "sess", "_sess"):
        s = getattr(m, attr, None)
        if s is not None and hasattr(s, "get_providers"):
            try:
                print("  实际使用 EP: %s" % s.get_providers(), flush=True)
            except Exception:
                pass
            break

    try:
        t0 = time.time()
        m.recognize(WAV)
        t_warm = time.time() - t0
        print("  预热 %.2fs" % t_warm, flush=True)
    except Exception as e:
        print("  !! 首次推理失败: %s: %s" % (type(e).__name__, str(e)[:500]), flush=True)
        return None

    times = []
    out = None
    for _ in range(3):
        t0 = time.time()
        out = m.recognize(WAV)
        times.append(time.time() - t0)
    med = float(np.median(times))
    print("  推理 中位 %.2fs (三次 %s)  RTFx=%.1f×"
          % (med, ["%.2f" % t for t in times], dur / med), flush=True)
    txt = out if isinstance(out, str) else str(out)
    print("  文本: %s" % txt[:400], flush=True)
    return dict(tag=tag, load=t_load, med=med, rtfx=dur / med, text=txt)


results = []
for tag, prov in [
    ("DML(GPU)", [("DmlExecutionProvider", {"device_id": 0})]),
    ("CPU", ["CPUExecutionProvider"]),
]:
    r = run(tag, prov)
    if r:
        results.append(r)

print("\n" + "=" * 72, flush=True)
print("汇总", flush=True)
for r in results:
    print("  %-10s 推理 %6.2fs  RTFx %6.1f×" % (r["tag"], r["med"], r["rtfx"]), flush=True)
    print("             %s" % r["text"][:200], flush=True)
print("=" * 72, flush=True)
print("DONE", flush=True)
