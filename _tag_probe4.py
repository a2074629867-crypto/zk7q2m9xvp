# -*- coding: utf-8 -*-
"""验证：① <rate factor="1.0"> 是否等价于不加标签（测"加标签"本身的副作用）；② factor=0.8 的精度。"""
import os
import subprocess
import sys
import time

ACPP = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT = "G:/_setup/_seam/tag"
BASE = "He walked to the window and looked out onto the copse."

CASES = [
    ("t_rate10", '<rate factor="1.0">%s</rate>' % BASE),
    ("t_rate08", '<rate factor="0.8">%s</rate>' % BASE),
    ("t_rate12", '<rate factor="1.2">%s</rate>' % BASE),
]


def run(tag, text):
    out = os.path.join(OUT, tag + ".wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--request-option", "max_tokens=300",
           "--seed", "42", "--num-inference-steps", "8",
           "--session-option", "dots_tts.mem_saver=true",
           "--out", out, "--metrics"]
    t0 = time.time()
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=600)
    print("%-10s wall=%5.1fs size=%7d" % (tag, time.time() - t0,
                                          os.path.getsize(out) if os.path.exists(out) else 0))
    sys.stdout.flush()


if __name__ == "__main__":
    for tag, text in CASES:
        run(tag, text)
