# -*- coding: utf-8 -*-
"""第三批 Charles 参考音：克制 / 内敛 / 低情绪。
上一批的坑：sad / wistful / tearful / timid 这类描述会把音色带软、带飘，
出来就是"幼态+女性化"。克制版必须明确 no emotion / flat / controlled。
输出 E:/tts-models/out/charles_ref3/
"""
import os
import subprocess
import sys

LAB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
CLI = os.path.join(LAB, "acpp_portable", "audiocpp_cli.exe")
MODEL = "E:/tts-models/Qwen3-TTS-VoiceDesign-GGUF"
OUT = "E:/tts-models/out/charles_ref3"

TEXT = ("He did not want to go into the house. He stood at the gate and looked back "
        "at the road, and thought about the long way he had come, and about the house "
        "that was not his.")

PALETTE = [
    ("r1_restrained",
     "An eleven-year-old English boy. Low, even voice with almost no emotion in it — controlled, measured, understated. He speaks slowly and never raises his pitch. British accent."),
    ("r2_deadpan",
     "A ten-year-old English boy with a low, flat, deadpan voice. Dry and quiet, no audible feeling in the delivery at all. British accent."),
    ("r3_held_back",
     "A boy of eleven holding his feelings back. Low steady voice, restrained and calm, never dramatic, no wobble and no whine. British accent."),
    ("r4_self_control",
     "An eleven-year-old English boy speaking with quiet self-control. Low pitch, even tempo, level tone, matter-of-fact. British accent."),
]

os.makedirs(OUT, exist_ok=True)
only = sys.argv[1:] or None
for i, (name, desc) in enumerate(PALETTE):
    if only and name not in only:
        continue
    out = os.path.join(OUT, name + ".wav")
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print("[skip]", name, flush=True)
        continue
    cmd = [CLI, "--task", "vdes", "--family", "qwen3_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--language", "english", "--instruct", desc,
           "--text", TEXT, "--seed", str(4100 + i), "--out", out]
    print("=" * 60, flush=True)
    print(name, flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout + r.stderr).splitlines()
            if any(k in l for k in ("audio_out", "duration", "error", "Error", "failed"))]
    print("  " + (" | ".join(tail[-2:]) if tail else "no metrics"), flush=True)
    print("  exists:", os.path.exists(out),
          os.path.getsize(out) if os.path.exists(out) else 0, "bytes", flush=True)
