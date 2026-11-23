# -*- coding: utf-8 -*-
"""第二批 Charles 参考音：明确要求低音，避开"童声=高音=女声感"。
输出 E:/tts-models/out/charles_ref2/
"""
import os
import subprocess
import sys

LAB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
CLI = os.path.join(LAB, "acpp_portable", "audiocpp_cli.exe")
MODEL = "E:/tts-models/Qwen3-TTS-VoiceDesign-GGUF"
OUT = "E:/tts-models/out/charles_ref2"

# ~32 词，约 11-12s；与上一批同长度便于对比
TEXT = ("He did not want to go into the house. He stood at the gate and looked back "
        "at the road, and thought about the long way he had come, and about the house "
        "that was not his.")

PALETTE = [
    ("c1_low_husky",
     "An eleven-year-old English boy with a low, husky voice for his age. Dark chesty timbre, quiet and serious. Definitely not a high or girlish voice. British accent."),
    ("c2_deep_calm",
     "A ten-year-old English boy with a deep, calm speaking voice. Low pitch, even and grave, speaking slowly and steadily. British accent."),
    ("c3_breaking",
     "A twelve-year-old boy whose voice is just beginning to break. Low, uneven, slightly rough. Quiet and sad. British accent."),
    ("c4_grave_narrator",
     "A young boy narrating a somber story. Low restrained voice, dark and unhurried, little expression. British accent."),
    ("c5_low_teen",
     "A thirteen-year-old boy with a low tenor voice, soft and melancholic, speaking gently and slowly. British accent."),
    ("c6_dull_low",
     "An eleven-year-old English boy with a dull, low monotone. Flat, tired, no brightness at all in the voice. British accent."),
    ("c7_chesty_whisper",
     "A small boy speaking in a low, chesty, breathy voice. Dark and intimate, almost a whisper. British accent."),
    ("c8_rough_low",
     "A boy of eleven with a rough, low, slightly hoarse voice. Serious, sad and quiet. British accent."),
]

os.makedirs(OUT, exist_ok=True)
only = sys.argv[1:] or None
for i, (name, desc) in enumerate(PALETTE):
    if only and name not in only:
        continue
    out = os.path.join(OUT, name + ".wav")
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print("[skip]", name)
        continue
    cmd = [CLI, "--task", "vdes", "--family", "qwen3_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--language", "english", "--instruct", desc,
           "--text", TEXT, "--seed", str(3100 + i), "--out", out]
    print("=" * 60, flush=True)
    print(name, flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout + r.stderr).splitlines()
            if any(k in l for k in ("audio_out", "duration", "error", "Error", "failed"))]
    print("  " + (" | ".join(tail[-2:]) if tail else "no metrics"), flush=True)
    print("  exists:", os.path.exists(out),
          os.path.getsize(out) if os.path.exists(out) else 0, "bytes", flush=True)
