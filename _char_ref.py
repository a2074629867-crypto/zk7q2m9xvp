# -*- coding: utf-8 -*-
"""用 Qwen3 VoiceDesign 生成 10s 长的 Charles 参考音（供 dots 当 voice_ref）"""
import os, json, subprocess

LAB = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
CLI = os.path.join(LAB, "acpp_portable", "audiocpp_cli.exe")
MODEL = "E:/tts-models/Qwen3-TTS-VoiceDesign-GGUF"
OUT  = "E:/tts-models/out/charles_ref"

TEXT = ("He did not want to go into the house. He stood at the gate and looked back "
        "at the road, and thought about the long way he had come, and about the house "
        "that was not his.")

PALETTE = [
    ("charles_lonely",
     "An eleven-year-old English boy. Thin, wistful child voice, speaking slowly and quietly. Sad and lonely. British accent."),
    ("charles_quiet",
     "A quiet ten-year-old English boy. Soft monotone child voice, low volume, little expression. Reserved and lonely. British accent."),
    ("charles_narrating",
     "A ten-year-old English boy telling a story. Clear, even child voice, natural and unforced. British accent."),
]

os.makedirs(OUT, exist_ok=True)
for name, desc in PALETTE:
    out = os.path.join(OUT, name + ".wav")
    cmd = [CLI, "--task", "vdes", "--family", "qwen3_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--language", "english", "--instruct", desc,
           "--text", TEXT, "--seed", "2016", "--out", out]
    print("=" * 60)
    print(name)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout + r.stderr).splitlines() if any(k in l for k in ("audio_out","duration","error","Error","failed"))]
    print("  " + (" | ".join(tail[-2:]) if tail else "no metrics"))
    print("  exists:", os.path.exists(out), os.path.getsize(out) if os.path.exists(out) else 0, "bytes")
