# -*- coding: utf-8 -*-
"""第四批：精确落点 140-175Hz（slightly low，不是 deep）+ 克制无情绪；另加 2 条法语男童。
输出 E:/tts-models/out/charles_ref4/
"""
import os
import subprocess
import sys

LAB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
CLI = os.path.join(LAB, "acpp_portable", "audiocpp_cli.exe")
MODEL = "E:/tts-models/Qwen3-TTS-VoiceDesign-GGUF"
OUT = "E:/tts-models/out/charles_ref4"

EN_TEXT = ("He did not want to go into the house. He stood at the gate and looked back "
           "at the road, and thought about the long way he had come, and about the house "
           "that was not his.")

FR_TEXT = ("Il ne voulait pas entrer dans la maison. Il restait devant le portail et "
           "regardait la route, en pensant au long chemin qu'il avait fait, et à cette "
           "maison qui n'était pas la sienne.")

JOBS = [
    # 英文克制 + 中等偏低
    ("m1_slightly_low", "english", EN_TEXT,
     "An eleven-year-old English boy with a slightly low, even voice. Calm, controlled, almost no emotion in the delivery. British accent."),
    ("m2_medium_low", "english", EN_TEXT,
     "A ten-year-old English boy with a medium-low, steady voice. Matter-of-fact and restrained, speaking quietly. British accent."),
    ("m3_plain_serious", "english", EN_TEXT,
     "A serious eleven-year-old English boy. Plain, even voice, a little low, speaking slowly without feeling. British accent."),
    ("m4_dry_level", "english", EN_TEXT,
     "A boy of eleven with a dry, level voice. Not high and not bright. Quiet, keeps his feelings to himself. British accent."),
    # 法语男童
    ("f1_french_boy", "french", FR_TEXT,
     "A French boy of eleven. Low, even, restrained voice with little emotion. Quiet and serious. Native French accent."),
    ("f2_french_boy_soft", "french", FR_TEXT,
     "A ten-year-old French boy with a soft, slightly low voice. Calm and understated, speaking slowly. Native French accent."),
]

os.makedirs(OUT, exist_ok=True)
only = sys.argv[1:] or None
for i, (name, lang, text, desc) in enumerate(JOBS):
    if only and name not in only:
        continue
    out = os.path.join(OUT, name + ".wav")
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print("[skip]", name, flush=True)
        continue
    cmd = [CLI, "--task", "vdes", "--family", "qwen3_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--language", lang, "--instruct", desc,
           "--text", text, "--seed", str(5100 + i), "--out", out]
    print("=" * 60, flush=True)
    print(name, lang, flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout + r.stderr).splitlines()
            if any(k in l for k in ("audio_out", "duration", "error", "Error", "failed"))]
    print("  " + (" | ".join(tail[-2:]) if tail else "no metrics"), flush=True)
    print("  exists:", os.path.exists(out),
          os.path.getsize(out) if os.path.exists(out) else 0, "bytes", flush=True)
